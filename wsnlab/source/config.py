## network properties
BROADCAST_NET_ADDR = 255
BROADCAST_NODE_ADDR = 255



## node properties
NODE_TX_RANGE = 100  # transmission range of nodes
NODE_ARRIVAL_MAX = 200  # max time to wake up


## simulation properties
SIM_NODE_COUNT = 80  # node count in simulation
SIM_NODE_PLACING_CELL_SIZE = 75  # cell size to place one node
SIM_DURATION = 40000  # simulation Duration in seconds
SIM_TIME_SCALE = 0.00001  #  The real time dureation of 1 second simualtion time
SIM_TERRAIN_SIZE = (1400, 1400)  #terrain size
SIM_TITLE = 'Data Collection Tree'  # title of visualization window
SIM_VISUALIZATION = True  # visualization active
SCALE = 1  # scale factor for visualization


## application properties
HEARTH_BEAT_TIME_INTERVAL = 100
REPAIRING_METHOD = 'ALL_ORPHAN' # 'ALL_ORPHAN', 'FIND_ANOTHER_PARENT'
EXPORT_CH_CSV_INTERVAL = 10  # simulation time units;
EXPORT_NEIGHBOR_CSV_INTERVAL = 10  # simulation time units;

CLUSTERHEAD_NEIGHBORS = False # False = Optimization
NODE_KILL_ALLOWED = False # X Nodes are Killed at Y Time
NODE_KILL_TIME = 8000
NODE_KILL_COUNT = 10

ENERGY_EN = 1 #ENABLE/DISABLE Energy
NODE_INITIAL_ENERGY = 10000 # initial energy of nodes
ENERGY_MIN = 100 #Minimum energy before node voluntarily leaves

if ENERGY_EN:
    NODE_TX_ENERGY_COST = 3 # energy cost for transmission
    NODE_RX_ENERGY_COST = 2 # energy cost for reception  
else:
    NODE_TX_ENERGY_COST = 0 # no energy loss
    NODE_RX_ENERGY_COST = 0 # no energy loss