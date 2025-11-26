Currently Steps 1-3 have been completed with more ideas on how to further optimize. 
Average Join Time was around 130ms but packet delay was only at 0ms which seems like a bug.

routing_tests_and_tables.txt: Holds information about all routing combinations between all nodes and the routes to get there.
Also includes information about each nodes neighbor table.

join_times.csv: Contains the timing for each node joining the network from the time it powered on.

packet_delays.csv: Contains information about all transmitted packets and their delays.

Primary Changes Completed in data_collection_tree.py and added extra time in config.py


# EE662Fall2021

WsnLab.py is a simulation library in Python based on WsnSimPy for self-organized networks.

# Requirements

You need to install the following packages.
- simpy



