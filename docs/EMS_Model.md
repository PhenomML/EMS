# Experiment Management System Model:

All systems that render and manage data have a model. The Experiment Management System has one too. So as to not impose needless constraints on the research process, we have endeavored to keep the model simple. It starts with a split between creating data and rendering data. Data is created by some server and deposited in a database. It is then examined by researchers who author Jupyter/Colab/DeepNote notebooks. The headless servers do not render views on the data. They store data in the database. Notebooks read the database and render views. This has the happy and intended consequence that researchers can easily see the live progress of their computation. The data can be computed using Python and then analyzed using R or Matlab or Python.

## EMS Model in More Detail:

A calculation, an experiment, is a confluence of assets -- code, data, servers, environments, projects, researchers, and funding. To remain flexible, responsibility for these various assets is divided between the researcher and the system. To start, the researcher must adopt managing their code and computational environment in a version control system. This is required for both efficacy in deploying code and reproducibility of computational experiments. Servers need to know which version of code, exactly, to run and research colleagues need to be able to recreate your environment to build upon it. Hence, code must be under version control and which version of the code being run is tracked by the system. Similarly, the computational environment must be explicitly managed. Why? So the server clusters can be constructed with the right versions of each library. As building a cluster takes time, which costs your funding agency money, it is wise to just include libraries needed. For example, you do not, in general, want to use your laptop's computational environment on your server. Why? It tends to include a bunch of libraries for rendering views of the data; which would then be replicated across, perhaps, hundreds of headless servers.

To further refine this concept, we need to explicitly identify systems and data that reifies these relationships. Unsurprisingly, the version control system provides the anchor of truth for creating the data. It contains the code and environment specification. If you know the hash that identifies the specific file commit, you should be able to recreate the experiment from scratch. While our initial version utilizes GitHub as the repository service, it could easily be mapped onto other services. As GitHub is inexpensive and hosts the vast majority of open source projects, it is a good match to our needs. In addition, it contains a lightweight web server to allow researchers to informally publish descriptions of their data/experiment.

The second system contains the database that keeps track of the experiments and hosts the resultant data. Initially, we are building this database on Google Big Query but it could easily be built on AWS DynamoDB or a common relational database, such as PostgreSQL.

The third system is an evanescent computational cluster. The cluster is created for the experiment. To save money, it is then, typically, deallocated. Some nodes, such as those on Stanford's Sherlock Supercomputer, are paid for by the lab's grants and should be used repeatedly. The EMS will support Sherlock, GCP, and AWS clusters. It also supports standalone servers and, of course, running on the researcher's laptop.

## EMS Model in Even More Detail:

The EMS database has four main tables: Experiment, Experimenter, Project, Funding. An Experiment will contain pointers to the Experimenter, his/her code, the server cluster/configuration, Project, and Funding. The Experimenter table will contain the experimenter's name, various account names, such as email address, GitHub account name, GCP and/or AWS account. The Project contains all of the structure items, such as Project and Funding along with each experiment. The Project table is the main driver of the "Tree of Notebooks" view of the lab's experiments. The Funding table is largely driven by the requirements of funding agencies. At minimum, it is likely a set of accounts to which the costs of computation are charged.
