#!/usr/bin/env python3

"""
EMS — Experiment Management System
====================================
A Python library for managing large-scale scientific computation experiments in the
Donoho Lab at Stanford. EMS coordinates parameter sweeps across Dask clusters (local,
SLURM, or Google Cloud) and persists results to SQLite, PostgreSQL (via Cloud SQL
Proxy), or Google BigQuery.

Architecture overview
---------------------
``Databases``
    Manages writing DataFrames to one or more storage backends simultaneously.
    Batches writes in memory, flushing when the accumulated data exceeds ``NUM_CELLS``
    (200 k cells) or a configurable time ``period`` has elapsed.

``EvalOnCluster``
    Wraps a Dask ``Client`` for dispatching experiment callables and collecting
    results asynchronously. Each result is pushed to the ``Databases`` instance and
    the future is released to free cluster memory.

``do_on_cluster()``
    Main orchestration function. Expands the experiment parameter grid, deduplicates
    against the database, shuffles remaining work, and dispatches via ``do_experiment()``.

Experiment dict format
----------------------
The experiment is expressed as a plain Python dict::

    experiment = {
        'table_name': 'my_experiment_table',   # required
        'params':     [{'a': [1, 2], 'b': [10, 20]}],  # one or more param dicts
        # OR 'multi_res': [...]   (alias for params)
        # OR 'parameters': {...}  (single param dict, no list wrapper)
        'stop_list':  [...],                    # optional: combos to skip
    }
"""

import copy
import itertools
import json
import logging
import os
import random
import time
from datetime import datetime, timezone, timedelta
from math import ceil, floor
from pathlib import Path

import pandas as pd
from pandas import DataFrame
import pandas_gbq
import pandas_gbq.exceptions
from dask.distributed import Client, worker_client, as_completed
from google.cloud.sql.connector import Connector
from google.oauth2 import service_account
from pg8000.dbapi import Connection
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from sqlalchemy.schema import MetaData

DB_URL = 'sqlite:///data/EMS.db3'
BATCH_SIZE = 4096
NUM_CELLS = 200 * 1000  # 200 rows x 1,000 columns. Slightly less than the values used on FarmShare
logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _touch_db_url(db_url: str):
    db_path = db_url.split('sqlite:///')
    if db_path[0] != db_url:  # If the string was found …
        p = Path(db_path[1])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch(exist_ok=True)


def _write_size_check(df: DataFrame) -> bool:
    t_row, n_col = df.shape
    return t_row * n_col > NUM_CELLS


def _safe_column_list(keys: list) -> str:
    """Return a comma-separated, double-quoted column list safe for SQL interpolation.

    Args:
        keys: Column names to quote.

    Returns:
        A SQL fragment like ``"col_a","col_b"`` suitable for use in a SELECT list.
    """
    return ','.join(f'"{k}"' for k in keys)


def _safe_table_name(table_name: str) -> str:
    """Return a double-quoted table name safe for SQL interpolation.

    Args:
        table_name: The unquoted table name.

    Returns:
        The table name wrapped in double quotes.
    """
    return f'"{table_name}"'


class Databases(object):
    """Manages writing experiment result DataFrames to one or more storage backends.

    Supports simultaneous writes to local SQLite, remote PostgreSQL (via SQLAlchemy),
    and Google BigQuery.  Results are accumulated in an in-memory buffer and flushed
    when the buffer exceeds ``NUM_CELLS`` cells or a configurable time period elapses.

    Args:
        table_name: Name of the destination table / BigQuery dataset table.  If
            ``None`` the instance is inert — no data will be written.
        remote: An optional SQLAlchemy ``Engine`` for a PostgreSQL (or other SQL)
            backend.
        credentials: Optional Google service-account credentials for BigQuery writes
            using ``pandas_gbq``.
        project_id: Optional GCP project ID for BigQuery writes without a credentials
            file.
        local_db: If ``True`` (default), create and write to the local SQLite database
            at ``data/EMS.db3``.  Pass ``False`` to disable local persistence.

    Attributes:
        results: Accumulated list of ``DataFrame`` objects pending a flush.
        last_save: UTC ``datetime`` of the most recent flush.
        table_name: Destination table name.
        local: SQLAlchemy engine for the local SQLite database, or ``None``.
        remote: SQLAlchemy engine for the remote database, or ``None``.
        credentials: Google service-account credentials, or ``None``.
        project_id: GCP project ID string, or ``None``.
    """

    def __init__(self, table_name: str = None,
                 remote: Engine = None,
                 credentials: service_account.credentials = None, project_id: str = None,
                 local_db: bool = True):
        self.results = []
        self.last_save = _now()
        if table_name is not None:
            self.table_name = table_name
            if local_db:
                _touch_db_url(DB_URL)
                self.local = create_engine(DB_URL, echo=False)
            else:
                self.local = None
            self.remote = remote
            self.credentials = credentials
            self.project_id = project_id
        else:
            self.table_name = None
            self.local = None
            self.remote = None
            self.credentials = None
            self.project_id = None

    def _push_to_database(self):
        df = pd.concat(self.results)
        df.reset_index(drop=True, inplace=True)
        logger.info(f'_push_to_database(): Number of DataFrames: {len(self.results)}; ' +
                    f'Length of DataFrames: {sum(len(result) for result in self.results)}\n{df}')
        self.results = []
        chunk_size = ceil(len(df) / 2) + 1 if _write_size_check(df) else len(df) + 1
        # Store locally for durability.
        if self.local is not None:
            try:
                with self.local.connect() as ldb:
                    df.to_sql(self.table_name, ldb, if_exists='append', method='multi', chunksize=chunk_size)
            except SQLAlchemyError as e:
                logger.error("%s", e)
        # Store remotely for flexibility.
        if self.remote is not None:
            try:
                with self.remote.connect() as rdb:
                    df.to_sql(self.table_name, rdb, if_exists='append', method='multi', chunksize=chunk_size)
            except SQLAlchemyError as e:
                logger.error("%s", e)
        if self.credentials is not None:
            try:
                pandas_gbq.to_gbq(df, f'EMS.{self.table_name}',
                                  if_exists='append', chunksize=chunk_size,
                                  progress_bar=False,
                                  credentials=self.credentials)
            except pandas_gbq.exceptions.GenericGBQException as e:
                logger.error("%s", e)
        elif self.project_id is not None:
            try:
                pandas_gbq.to_gbq(df, f'EMS.{self.table_name}',
                                  if_exists='append', chunksize=chunk_size,
                                  progress_bar=False,
                                  project_id=self.project_id)
            except pandas_gbq.exceptions.GenericGBQException as e:
                logger.error("%s", e)
        df = None

    def _results_size_check(self) -> bool:
        if len(self.results) > 0:
            _, n_col = self.results[0].shape
            t_row = sum(len(result) for result in self.results)
            return t_row * n_col > NUM_CELLS
        else:
            return False

    def push(self, result: DataFrame, period=60.0):
        """Append a result DataFrame and flush if the size or time threshold is exceeded.

        Args:
            result: A ``DataFrame`` to buffer.  ``None`` is silently ignored.
            period: Flush interval in seconds.  Defaults to 60.
        """
        now = _now()
        if result is not None:
            self.results.append(result)
        if self._results_size_check() or (now - self.last_save) > timedelta(seconds=period):
            self._push_to_database()
            self.last_save = now

    def final_push(self):
        """Flush any remaining buffered results and dispose of all database connections.

        Note:
            This method also disposes of the SQLAlchemy engines and clears credentials,
            making the instance unusable for further writes.  A separate ``shutdown()``
            method for the Dask client is planned for v2.
        """
        if len(self.results) > 0:
            self._push_to_database()
        if self.local is not None:
            self.local.dispose()
        self.local = None
        if self.remote is not None:
            self.remote.dispose()
        self.remote = None
        self.credentials = None
        self.project_id = None

    def _first_result(self) -> DataFrame | None:
        return self.results[0] if len(self.results) > 0 else None

    def push_batch(self, period=60.0):
        """Flush buffered results if the size or time threshold is exceeded.

        Unlike ``push()``, this method does not append a new result first.  It is
        intended to be called after a batch of ``batch_result()`` calls.

        Args:
            period: Flush interval in seconds.  Defaults to 60.
        """
        now = _now()
        if self._results_size_check() or (now - self.last_save) > timedelta(seconds=period):
            self._push_to_database()
            self.last_save = now

    def batch_result(self, result: DataFrame):
        """Buffer a result DataFrame; flush early if the buffer is already large.

        Intended for use inside a batch-collection loop alongside ``push_batch()``.

        Args:
            result: A ``DataFrame`` to buffer.  ``None`` is silently ignored.
        """
        if result is not None:
            self.results.append(result)
        if self._results_size_check():  # If the batch write is already large, push it.
            logger.info(f'batch_result(): Early Push: Number of Columns: {result.shape[1]}; ' +
                        f'Length of DataFrames: {sum(len(df) for df in self.results)}')
            self.push_batch()

    def read_table(self) -> DataFrame:
        """Read the entire result table from the first available backend.

        Backends are tried in priority order: remote SQL → BigQuery (credentials) →
        BigQuery (project_id) → local SQLite.

        Returns:
            A ``DataFrame`` containing all rows, or ``None`` if the table does not
            exist or no backend is configured.
        """
        df = None
        if self.table_name is not None:
            if self.remote is not None:
                try:
                    df = pd.read_sql_query(
                        text(f'SELECT * FROM {_safe_table_name(self.table_name)}'),
                        self.remote
                    )
                except (ValueError, OperationalError) as e:
                    logger.error(f'{e}')
                    df = None
            elif self.credentials is not None:
                try:
                    df = pandas_gbq.read_gbq(f'SELECT * FROM `EMS.{self.table_name}`',
                                             credentials=self.credentials, progress_bar_type=None)
                except pandas_gbq.exceptions.GenericGBQException as e:
                    logger.error(f'{e}')
                    df = None
            elif self.project_id is not None:
                try:
                    df = pandas_gbq.read_gbq(f'SELECT * FROM `EMS.{self.table_name}`',
                                             project_id=self.project_id, progress_bar_type=None)
                except pandas_gbq.exceptions.GenericGBQException as e:
                    logger.error(f'{e}')
                    df = None
            elif self.local is not None:
                try:
                    df = pd.read_sql_table(self.table_name, self.local)
                except ValueError:
                    df = None
        return df

    def read_params(self, params: list) -> DataFrame:
        """Read the distinct parameter combinations already stored in the table.

        Used by ``do_on_cluster()`` to determine which parameter combos have already
        been computed so they can be filtered out before dispatching new work.

        Column and table names are safely quoted to prevent SQL injection.

        Args:
            params: A list of parameter dicts (as produced by ``unroll_parameters_gpt()``).
                The keys of the first dict determine which columns are fetched.  If the
                list is empty, the full table is returned via ``read_table()``.

        Returns:
            A ``DataFrame`` of distinct parameter combos already in the database, or
            ``None`` if the table does not exist or no backend is configured.
        """
        df = None
        if self.table_name is not None:
            if len(params) > 0:
                keys = sorted(params[0].keys())
                col_list = _safe_column_list(keys)
                tbl = _safe_table_name(self.table_name)
                if self.remote is not None:
                    try:
                        df = pd.read_sql_query(
                            text(f'SELECT DISTINCT {col_list} FROM {tbl}'),
                            self.remote
                        )
                    except (ValueError, OperationalError) as e:
                        logger.error(f'{e}')
                        df = None
                elif self.credentials is not None:
                    try:
                        df = pandas_gbq.read_gbq(
                            f'SELECT DISTINCT {col_list} FROM `EMS.{self.table_name}`',
                            credentials=self.credentials, progress_bar_type=None
                        )
                    except pandas_gbq.exceptions.GenericGBQException as e:
                        logger.error(f'{e}')
                        df = None
                elif self.project_id is not None:
                    try:
                        df = pandas_gbq.read_gbq(
                            f'SELECT DISTINCT {col_list} FROM `EMS.{self.table_name}`',
                            project_id=self.project_id, progress_bar_type=None
                        )
                    except pandas_gbq.exceptions.GenericGBQException as e:
                        logger.error(f'{e}')
                        df = None
                elif self.local is not None:
                    try:
                        df = pd.read_sql_query(
                            text(f'SELECT DISTINCT {col_list} FROM {tbl}'),
                            self.local
                        )
                    except (ValueError, OperationalError) as e:
                        logger.error(f'{e}')
                        df = None
            else:
                df = self.read_table()
        return df


# The Cloud SQL Python Connector can be used along with SQLAlchemy using the
# 'creator' argument to 'create_engine'
def create_remote_connection_engine() -> Engine:
    """Create a SQLAlchemy engine for a Cloud SQL PostgreSQL instance.

    Reads connection parameters from environment variables:

    - ``POSTGRES_CONNECTION_NAME`` — Cloud SQL instance connection name
    - ``POSTGRES_USER`` — database user
    - ``POSTGRES_PASS`` — database password
    - ``POSTGRES_DB`` — database name

    Returns:
        A SQLAlchemy ``Engine`` configured with ``pool_pre_ping=True`` to
        reestablish stale connections automatically.
    """
    def get_conn() -> Connection:
        connector = Connector()
        connection: Connection = connector.connect(
            os.environ["POSTGRES_CONNECTION_NAME"],
            "pg8000",
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASS"],
            db=os.environ["POSTGRES_DB"],
        )
        return connection

    engine = create_engine(
        "postgresql+pg8000://",
        creator=get_conn,
        echo=False,
        pool_pre_ping=True  # Force reestablishing the connection.
    )
    engine.dialect.description_encoding = None
    return engine


def active_remote_engine() -> (Engine, MetaData):
    """Create and validate a remote PostgreSQL engine by reflecting the schema.

    Calls ``create_remote_connection_engine()`` and immediately issues a metadata
    reflection query to verify the connection is live.

    Returns:
        A ``(Engine, MetaData)`` tuple if the connection succeeds, or
        ``(None, None)`` if a ``SQLAlchemyError`` is raised.
    """
    remote = create_remote_connection_engine()
    metadata = MetaData()
    try:
        metadata.reflect(remote)  # Causes a DB query.
        return remote, metadata
    except SQLAlchemyError as e:
        logger.error("%s", e)
        remote.dispose()
    return None, None


def get_gbq_credentials(cred_name: str = 'hs-deep-lab-donoho-3d5cf4ffa2f7.json') -> service_account.Credentials:
    """Load Google service-account credentials from ``~/.config/gcloud/``.

    Args:
        cred_name: Filename of the JSON key file inside ``~/.config/gcloud/``.
            Defaults to the Donoho Lab service account key.

    Returns:
        A ``google.oauth2.service_account.Credentials`` object ready for use
        with ``pandas_gbq`` or other Google Cloud client libraries.
    """
    path = f'~/.config/gcloud/{cred_name}'  # Pandas-GBQ-DataSource
    expanded_path = os.path.expanduser(path)
    credentials = service_account.Credentials.from_service_account_file(expanded_path)
    return credentials


class EvalOnCluster(object):
    """Dispatches experiment callables to a Dask cluster and collects results.

    Wraps a Dask ``Client`` and a ``Databases`` instance.  Results are buffered in
    the ``Databases`` object and flushed according to its size/time thresholds.
    Each Dask future is released after its result is collected to free cluster memory.

    Args:
        client: A live Dask ``Client``.
        table_name: Destination table name passed to ``Databases``.
        credentials: Optional Google service-account credentials for BigQuery.
        local_db: If ``True`` (default), write to local SQLite.

    Attributes:
        db: The ``Databases`` instance used for persistence.
        client: The Dask ``Client``.
        computations: An ``as_completed`` iterator over ``(future, result)`` pairs,
            or ``None`` before ``eval_params_list()`` has been called.
        keys: Sorted list of parameter keys, set on first call to ``key_from_params()``.
    """

    def __init__(self, client: Client,
                 table_name: str = None, credentials: service_account.credentials = None,
                 local_db: bool = True):
        self.db = Databases(table_name, None, credentials, None, local_db=local_db)
        self.client = client
        self.credentials = credentials
        self.computations = None  # Iterable returning (future, df).
        self.keys = None

    def key_from_params(self, params: dict) -> tuple:
        """Extract a hashable key tuple from a parameter dict.

        The key ordering is determined by the sorted parameter names on the first
        call; subsequent calls must use dicts with the same set of keys.

        Args:
            params: A parameter dict whose values will form the key.

        Returns:
            A tuple of parameter values in sorted-key order.

        Raises:
            ValueError: If ``params`` has different keys than those established on
                the first call.
        """
        if self.keys is None:
            self.keys = sorted(params.keys())
        else:
            incoming = sorted(params.keys())
            if incoming != self.keys:
                raise ValueError(
                    f'key_from_params(): parameter keys changed. '
                    f'Expected {self.keys}, got {incoming}.'
                )
        return tuple(params[k] for k in self.keys)

    def eval_params_list(self, instance: callable, params: [dict]) -> [tuple]:
        """Dispatch a list of parameter dicts to the cluster for evaluation.

        Each dict is passed as ``**kwargs`` to ``instance`` via ``client.map()``.
        Results are fed into an ``as_completed`` iterator that is consumed by
        ``__iter__`` / ``next_batch()``.

        Args:
            instance: The callable to invoke on each worker.
            params: A list of parameter dicts; each becomes one Dask task.

        Returns:
            A list of key tuples (one per param dict) in the same order as ``params``.
            The return value is informational; callers typically ignore it.
        """
        futures = self.client.map(lambda p: instance(**p), params)  # To isolate kwargs, use a lambda function.
        if self.computations is None:
            self.computations = as_completed(futures, with_results=True)
        else:
            self.computations.update(futures)
        return [self.key_from_params(p) for p in params]

    def __iter__(self):
        return self

    def __next__(self):
        """Return the next completed result as ``(DataFrame, key_tuple)``.

        Raises:
            RuntimeError: If called before ``eval_params_list()``.
            StopIteration: When all submitted futures have been consumed.
        """
        if self.computations is None:
            raise RuntimeError('__next__() called before eval_params_list(); no computations pending.')
        future, result = self.computations.__next__()
        self.db.push(result)
        future.release()  # EP function; release the data; will not be reused.
        values = result[self.keys].to_numpy()
        return result, tuple(v for v in values[0])

    def next_batch(self, period=60.0) -> list:
        """Collect all currently-completed futures without blocking.

        Calls ``as_completed.next_batch(block=False)``, buffers each result via
        ``db.batch_result()``, then triggers a conditional flush via ``db.push_batch()``.

        Failed futures (where ``result`` is ``None``) are logged as warnings and
        skipped rather than raising — non-blocking batch semantics are preserved.

        Args:
            period: Flush interval forwarded to ``push_batch()``.  Defaults to 60 s.

        Returns:
            A list of ``(DataFrame, key_tuple)`` pairs for successful results.

        Raises:
            RuntimeError: If called before ``eval_params_list()``.
        """
        if self.computations is None:
            raise RuntimeError('next_batch() called before eval_params_list(); no computations pending.')
        batch = self.computations.next_batch(block=False)
        for future, result in batch:
            if result is None:
                logger.warning(f'next_batch(): future {future.key!r} raised an exception; result skipped.')
            self.db.batch_result(result)
            future.release()  # As these are Embarrassingly Parallel tasks, clean up memory.
        self.db.push_batch(period=period)
        return [(result, tuple(v for v in result[self.keys].to_numpy()[0]))
                for _, result in batch if result is not None]

    def final_push(self):
        """Flush remaining buffered results and shut down the Dask client.

        Note:
            This method combines two concerns: flushing the ``Databases`` buffer
            (``db.final_push()``) and shutting down the Dask client
            (``client.shutdown()``).  A separate ``shutdown()`` method is planned
            for v2 to allow finer-grained lifecycle control.
        """
        self.db.final_push()
        self.client.shutdown()


def on_worker() -> bool:
    """Check whether the current code is executing on a Dask worker.

    Returns:
        ``True`` if running inside a Dask worker context, ``False`` otherwise.
    """
    import distributed.worker

    try:
        _ = distributed.worker.get_worker()
        return True
    except ValueError:
        return False


def get_dataset(key: str) -> DataFrame:
    """Retrieve a named dataset from the Dask scheduler.

    Works both on workers (via ``worker_client``) and on the client side
    (via ``Client.current``).

    Args:
        key: The dataset name as registered with ``client.publish_dataset()``.

    Returns:
        The stored ``DataFrame``, or ``None`` if the key does not exist.
    """
    if on_worker():
        with worker_client() as wc:
            df = wc.get_dataset(name=key, default=None)
    else:
        wc = Client.current(allow_global=True)
        df = wc.get_dataset(name=key, default=None)
    return df


def unroll_parameters_gpt(parameters: dict) -> list:
    """Expand a parameter dict into a flat list of all Cartesian-product combinations.

    Uses ``itertools.product`` for efficiency.

    Args:
        parameters: A dict mapping parameter names to lists (or array-like objects)
            of values.  For example::

                {
                    'm': [50],
                    'n': [1275, 2550, 3825],
                    'mc': list(range(50)),
                }

    Returns:
        A list of dicts, each representing one parameter combination.  The length
        equals the product of the lengths of all value lists.  Returns an empty
        list if ``parameters`` is empty.
    """
    if not parameters:
        return []
    unrolled = []

    # Get all possible combinations of values from the lists
    combinations = list(itertools.product(*parameters.values()))

    # Create dictionaries with keys and one combination of values
    for combo in combinations:
        combined = {key: value for key, value in zip(parameters.keys(), combo)}
        unrolled.append(combined)
    return unrolled


def remove_stop_list(unrolled: list, stop: list) -> list:
    """Remove parameter combos that appear in the stop list.

    Performs an exact match on all key-value pairs.  Combos with a different
    number of keys are never considered a match (and are kept).

    Args:
        unrolled: The full list of parameter dicts to filter.
        stop: A list of parameter dicts representing combos to exclude.

    Returns:
        A new list containing only those dicts from ``unrolled`` that do not
        appear in ``stop``.
    """
    result = []
    sl = stop.copy()  # Copy the stop_list to allow it to shrink as items are found and removed.
    for param in unrolled:
        for s_param in sl:
            if len(param) == len(s_param):  # Mismatched lengths are never equal; keep the param.
                for k, v in s_param.items():
                    if param[k] != v:
                        break
                else:  # no_break => all (k, v) are equal. param is IN the stop_list.
                    sl.remove(s_param)
                    break
        else:  # no_break => param is NOT in the stop_list.
            result.append(param)
    return result


def timestamp() -> int:
    return floor(_now().timestamp())


def write_json(d: dict, fn: str):
    """Serialize a dict to a JSON file.

    Args:
        d: The dict to serialize.
        fn: Output file path.
    """
    with open(fn, 'w') as json_file:
        json.dump(d, json_file, indent=4)


def read_json(fn: str) -> dict:
    """Deserialize a JSON file to a dict.

    Args:
        fn: Input file path.

    Returns:
        The deserialized dict.
    """
    with open(fn, 'r') as json_file:
        d = json.load(json_file)
    return d


def record_experiment(experiment: dict):
    """Serialize the experiment dict to a timestamped JSON file.

    The file is written to the current working directory as
    ``<table_name>-<unix_timestamp>.json``.

    Note:
        This function always writes to the process CWD, which may not be the
        project root when running on a cluster.  This is a known limitation;
        an experiment registry (Phase 2, R-9) will supersede it.

    Args:
        experiment: The experiment configuration dict.  Must contain a
            ``'table_name'`` key; if absent, nothing is written.
    """
    table_name = experiment.get('table_name', None)
    if table_name is not None:
        now_ts = timestamp()
        write_json(experiment, table_name + f'-{now_ts}.json')


def unroll_experiment(experiment: dict) -> list:
    """Expand an experiment dict into a flat list of parameter dicts.

    Supports three parameter-specification styles, checked in order:

    - ``'params'``: a list of parameter dicts — each is unrolled separately and
      the results are concatenated.
    - ``'multi_res'``: alias for ``'params'``.
    - ``'parameters'``: a single parameter dict (no list wrapper).

    If a ``'stop_list'`` key is present, those combos are removed from the result.

    Args:
        experiment: The experiment configuration dict.

    Returns:
        A flat list of parameter dicts, one per unique parameter combination,
        with stop-list entries removed.
    """
    parameters = []
    if params := experiment.get('params', None):
        for p in params:
            parameters.extend(unroll_parameters_gpt(p))
    elif multi_res := experiment.get('multi_res', None):
        for p in multi_res:
            parameters.extend(unroll_parameters_gpt(p))
    elif params := experiment.get('parameters', None):
        parameters = unroll_parameters_gpt(params)
    if stop_list := experiment.get('stop_list', None):
        parameters = remove_stop_list(parameters, stop_list)
    return parameters


def dedup_experiment(df: DataFrame, params: list) -> list:
    """Filter ``params`` to exclude combos already present in ``df``.

    Compares each parameter dict in ``params`` against the rows of ``df`` using
    the sorted parameter keys.  Both already-stored combos and duplicates within
    ``params`` itself are removed (first occurrence wins).

    Args:
        df: A ``DataFrame`` of already-computed parameter combos (as returned by
            ``Databases.read_params()``).
        params: The full list of parameter dicts to filter.

    Returns:
        A list containing only those dicts whose key-value tuples do not appear
        in ``df``.
    """
    dedup = []
    if len(params) > 0:
        keys = sorted(params[0].keys())
        df_values = set(tuple(row) for row in df[keys].to_numpy())

        for p in params:
            values = tuple(p[k] for k in keys)
            if values not in df_values:
                dedup.append(p)
                df_values.add(values)
    return dedup


def dedup_experiment_from_db(experiment: dict, remote: Engine = None,
                             credentials: service_account.credentials = None) -> list:
    """Return the parameter combinations from ``experiment`` not yet in the database.

    Convenience wrapper that creates a ``Databases`` instance, calls
    ``read_params()`` and ``dedup_experiment()``, and returns the remainder.

    Args:
        experiment: The experiment configuration dict.
        remote: Optional SQLAlchemy engine for a remote PostgreSQL backend.
        credentials: Optional Google service-account credentials for BigQuery.

    Returns:
        A list of parameter dicts that have not yet been computed.
    """
    # Read the DB level parameters.
    table_name = experiment.get('table_name', None)
    db = Databases(table_name, remote, credentials)

    # Prepare parameters.
    parameters = unroll_experiment(experiment)
    df = db.read_params(parameters)
    if df is not None and len(df.index) > 0:
        parameters = dedup_experiment(df, parameters)
    return parameters  # Return the parameters not yet calculated.


def do_experiment(instance: callable, parameters: list, db: Databases, client: Client):
    """Dispatch ``instance`` for each parameter dict and collect results into ``db``.

    Uses ``client.map()`` with ``as_completed().batches()`` for efficient streaming
    collection.  Progress is logged every 10 completed results.  The ``db`` is
    flushed after each batch and given a final push at the end.

    Args:
        instance: The callable to invoke on the cluster.  Called as
            ``instance(**params)`` for each dict in ``parameters``.
        parameters: The list of parameter dicts to evaluate.
        db: The ``Databases`` instance used for persistence.
        client: The Dask ``Client`` to use for dispatching.
    """
    instance_count = len(parameters)
    i = 0
    logger.info(f'Number of Instances to calculate: {instance_count}')
    # Start the computation.
    tick = time.perf_counter()
    futures = client.map(lambda p: instance(**p), parameters, batch_size=BATCH_SIZE)
    for batch in as_completed(futures, with_results=True).batches():
        for future, result in batch:
            i += 1
            if not (i % 10):  # Log results every tenth output
                tock = time.perf_counter() - tick
                remaining_count = instance_count - i
                s_i = tock / i
                logger.info(f'Count: {i}; Time: {round(tock)}; Seconds/Instance: {s_i:0.4f}; ' +
                            f'Remaining (s): {round(remaining_count * s_i)}; Remaining Count: {remaining_count}')
                logger.info(result)
            db.batch_result(result)
            future.release()  # As these are Embarrassingly Parallel tasks, clean up memory.
        db.push_batch()
    db.final_push()
    total_time = time.perf_counter() - tick
    logger.info(f"Performed experiment in {total_time:0.4f} seconds")
    if instance_count > 0:
        logger.info(f"Count: {instance_count}, Seconds/Instance: {(total_time / instance_count):0.4f}")


def do_on_cluster(experiment: dict, instance: callable, client: Client,
                  remote: Engine = None,
                  credentials: service_account.credentials = None, project_id: str = None):
    """Run an experiment on a Dask cluster with automatic deduplication.

    This is the main entry point for executing parameter sweeps.  It:

    1. Creates a ``Databases`` instance for persistence.
    2. Serializes the experiment dict to a timestamped JSON file (``record_experiment``).
    3. Expands the parameter grid (``unroll_experiment``).
    4. Queries the database for already-computed combos (``db.read_params``).
    5. Filters out completed combos (``dedup_experiment``).
    6. Shuffles the remaining parameters to reduce contention.
    7. Dispatches and collects results (``do_experiment``).
    8. Shuts down the Dask client.

    Experiment dict format::

        experiment = {
            'table_name':  str,           # required — destination table name
            'params':      [dict, ...],   # list of parameter dicts (Cartesian product per dict)
            # OR 'multi_res': [dict, ...] # alias for 'params'
            # OR 'parameters': dict       # single parameter dict (no list wrapper)
            'stop_list':   [dict, ...],   # optional — parameter combos to skip
        }

    Args:
        experiment: The experiment configuration dict (see format above).
        instance: The callable to invoke for each parameter combination.  Must
            accept the parameter dict's keys as keyword arguments and return a
            ``DataFrame``.
        client: A live Dask ``Client``.
        remote: Optional SQLAlchemy engine for a remote PostgreSQL backend.
        credentials: Optional Google service-account credentials for BigQuery.
        project_id: Optional GCP project ID for BigQuery (used when no credentials
            file is available).
    """
    logger.info(f'{client}')
    # Read the DB level parameters.
    table_name = experiment.get('table_name', None)
    db = Databases(table_name, remote, credentials, project_id)

    # Save the experiment domain.
    record_experiment(experiment)

    # Prepare parameters.
    parameters = unroll_experiment(experiment)
    df = db.read_params(parameters)
    if df is not None and len(df.index) > 0:
        parameters = dedup_experiment(df, parameters)
    df = None  # Free up the DataFrame.
    if len(parameters) > 0:
        random.shuffle(parameters)
        do_experiment(instance, parameters, db, client)
    else:
        logger.warning('Database is complete.')
    client.shutdown()
