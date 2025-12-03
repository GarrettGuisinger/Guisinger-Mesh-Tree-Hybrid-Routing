import random
from enum import Enum
import sys
sys.path.insert(1, '.')
from source import wsnlab_vis as wsn
import math
from source import config
from collections import Counter


import csv 

# Track where each node is placed
NODE_POS = {}  # {node_id: (x, y)}

# --- tracking containers ---
ALL_NODES = []            
CLUSTER_HEADS = []
ROLE_COUNTS = Counter()  
NEIGHBOR_VALIDITY_TIMEOUT = 300

# Tracking Info
PACKET_LOGS = []
JOIN_TIMES = []

ROUTER_CHILD_CHECK_INTERVAL = 50

def _addr_str(a): return "" if a is None else str(a)
def _role_name(r): return r.name if hasattr(r, "name") else str(r)

def test_all_registered_nodes():
    """Test message routing between ALL registered nodes"""
    print("\n" + "="*60)
    print("AUTOMATIC ALL-PAIRS NEIGHBOR TABLE TESTING")
    print("="*60)
    
    registered_nodes = []
    for node in sim.nodes:
        if hasattr(node, 'addr') and node.addr is not None:
            registered_nodes.append(node)
    
    if len(registered_nodes) < 2:
        print("Error: Need at least 2 registered nodes")
        return
    
    print(f"\nFound {len(registered_nodes)} registered nodes")
    print(f"Testing {len(registered_nodes) * (len(registered_nodes) - 1)} routes...")
    print("-" * 60)
    
    test_count = 0
    reachable_count = 0
    out_of_range_count = 0
    
    for source_node in registered_nodes:
        for dest_node in registered_nodes:
            if source_node.id == dest_node.id:
                continue
            
            test_count += 1
            print(f"\nTest {test_count}: Node {source_node.id} → Node {dest_node.id}")
            
            # Check if in neighbor table
            if dest_node.id in source_node.neighbors_table:
                neighbor_info = source_node.neighbors_table[dest_node.id]
                next_hop = neighbor_info.get('next_hop')
                
                if next_hop is None:
                    print(f"  Range: DIRECT (1-hop)")
                    reachable_count += 1
                else:
                    print(f"  Range: 2-hop via Node {next_hop}")
                    reachable_count += 1
                
                source_node.send_test_message(dest_node.id, f"Test #{test_count}")
            else:
                print(f"  Range: OUT OF RANGE (not in neighbor table)")
                out_of_range_count += 1
    
    print("\n" + "="*60)
    print(f"TESTING COMPLETE")
    print(f"  Total tests: {test_count}")
    print(f"  Reachable: {reachable_count}")
    print(f"  Out of range: {out_of_range_count}")
    print("="*60)

Roles = Enum('Roles', 'UNDISCOVERED UNREGISTERED ROOT REGISTERED CLUSTER_HEAD ROUTER')
"""Enumeration of roles"""

###########################################################
class SensorNode(wsn.Node):
    """SensorNode class is inherited from Node class in wsnlab.py.
    It will run data collection tree construction algorithms.

    Attributes:
        role (Roles): role of node
        is_root_eligible (bool): keeps eligibility to be root
        c_probe (int): probe message counter
        th_probe (int): probe message threshold
        neighbors_table (Dict): keeps the neighbor information with received heart beat messages
    """

    ###################
    def init(self):
        """Initialization of node. Setting all attributes of node.
        At the beginning node needs to be sleeping and its role should be UNDISCOVERED.

        Args:

        Returns:

        """
        self.scene.nodecolor(self.id, 1, 1, 1) 
        self.sleep()
        self.addr = None
        self.ch_addr = None
        self.parent_gui = None
        self.root_addr = None
        self.set_role(Roles.UNDISCOVERED)
        self.is_root_eligible = True if self.id == ROOT_ID else False
        self.c_probe = 0
        self.th_probe = 10 
        self.hop_count = 2
        self.neighbors_table = {} 
        self.candidate_parents_table = []
        self.child_networks_table = {}
        self.members_table = []
        self.received_JR_guis = [] 
        self.received_probes = {}
        self.become_router = False
        self.pending_promotions = set()
        self.can_promote = False
        self.changeRole = True
        self.test_queue = [] 
        self.test_index = 0  
        self.test_output_file = None
        self.probe_start_time = None 
        self.last_parent_heartbeat = None
        self.ch_collision_count = {} 
        self.ch_collision_threshold = 3
        self.ch_collision_timers = {}


    ###################
    def run(self):
        """Setting the arrival timer to wake up after firing.

        Args:

        Returns:

        """
        self.set_timer('TIMER_ARRIVAL', self.arrival)

    ###################

    def set_role(self, new_role, *, recolor=True):
        """Central place to switch roles, keep tallies, and (optionally) recolor."""
        old_role = getattr(self, "role", None)
        if old_role is not None:
            ROLE_COUNTS[old_role] -= 1
            if ROLE_COUNTS[old_role] <= 0:
                ROLE_COUNTS.pop(old_role, None)
        ROLE_COUNTS[new_role] += 1
        self.role = new_role

        if recolor:
            if new_role == Roles.UNDISCOVERED:
                self.scene.nodecolor(self.id, 1, 1, 1)
            elif new_role == Roles.UNREGISTERED:
                self.scene.nodecolor(self.id, 1, 1, 0)
            elif new_role == Roles.REGISTERED:
                self.scene.nodecolor(self.id, 0, 1, 0)
            elif new_role == Roles.CLUSTER_HEAD:
                self.scene.nodecolor(self.id, 0, 0, 1)
                self.draw_tx_range()
            elif new_role == Roles.ROOT:
                self.scene.nodecolor(self.id, 0, 0, 0)
                self.set_timer('TIMER_EXPORT_CH_CSV', config.EXPORT_CH_CSV_INTERVAL)
                self.set_timer('TIMER_EXPORT_NEIGHBOR_CSV', config.EXPORT_NEIGHBOR_CSV_INTERVAL)
            elif new_role == Roles.ROUTER:
                self.scene.nodecolor(self.id, 1, 0, 1)
                self.erase_tx_range()
                
    def become_unregistered(self):
        """Reset node to initial unregistered state and attempt to rejoin."""
        if self.role != Roles.UNDISCOVERED:
            self.kill_all_timers()
            self.log('I became UNREGISTERED')
        
        # Visual reset
        self.scene.nodecolor(self.id, 1, 1, 0)
        self.erase_parent()
        
        # Reset ALL network state to initial conditions
        self.addr = None
        self.ch_addr = None
        self.parent_gui = None
        self.root_addr = None
        self.set_role(Roles.UNREGISTERED)
        self.c_probe = 0
        self.th_probe = 10
        self.hop_count = 2
        self.neighbors_table = {}
        self.candidate_parents_table = []
        self.child_networks_table = {}
        self.members_table = []
        self.received_JR_guis = []
        self.received_probes = {}
        self.become_router = False
        self.pending_promotions = set()
        self.can_promote = False
        self.changeRole = True
        self.ch_collision_count = {}
        self.ch_collision_timers = {} 
        
        self.probe_start_time = self.now
        self.set_timer('TIMER_REJOIN_DELAY', 200)
        

    ###################
    def update_neighbor(self, pck):
        sender_gui = pck['gui']
        sender_addr = pck.get('addr')
        sender_hop_count = pck.get('hop_count', 0)
        sender_role = pck.get('role') 

        # Neighbor table automatically tracks last_heard time
        self.neighbors_table[sender_gui] = {
            'addr': sender_addr,
            'hop_count': sender_hop_count,
            'source': pck.get('source'),
            'ch_addr': pck.get('ch_addr'),
            'role': sender_role,
            'last_heard': self.now,
            'next_hop': None
        }

        sender_neighbors = pck.get('neighbors', [])
        for neighbor_of_sender in sender_neighbors:
            if neighbor_of_sender == self.id:
                continue
            
            existing = self.neighbors_table.get(neighbor_of_sender)
            if existing and existing.get('next_hop') is None:
                continue

            neighbor_addr = None
            for node in sim.nodes:
                if node.id == neighbor_of_sender and hasattr(node, 'addr'):
                    neighbor_addr = node.addr
                    break
            
            self.neighbors_table[neighbor_of_sender] = {
                'addr': neighbor_addr,
                'hop_count': sender_hop_count + 1,
                'last_heard': self.now,
                'next_hop': sender_gui,
                'role': None  
            }
        
        if sender_addr is not None: 
            if sender_gui not in self.members_table:  
                if sender_gui not in self.candidate_parents_table:
                    self.candidate_parents_table.append(sender_gui)


    def get_neighbor_status(self, gui):
        """Get neighbor info with validity status."""
        if gui not in self.neighbors_table:
            return None
        
        entry = self.neighbors_table[gui]
        time_since_heard = self.now - entry['last_heard']
        is_valid = time_since_heard <= NEIGHBOR_VALIDITY_TIMEOUT
        
        return {
            'addr': entry['addr'],
            'last_heard': entry['last_heard'],
            'valid': is_valid,
            'next_hop': entry['next_hop']
        }

    def get_neighbors_with_validity(self):
        """Get all neighbors with validity status."""
        result = {}
        for gui, entry in self.neighbors_table.items():
            time_since_heard = self.now - entry['last_heard']
            is_valid = time_since_heard <= NEIGHBOR_VALIDITY_TIMEOUT
            result[gui] = {
                'addr': entry['addr'],
                'last_heard': entry['last_heard'],
                'valid': is_valid,
                'next_hop': entry['next_hop']
            }
        return result

    def check_parent_alive(self):
        """Check if parent is still responding using existing neighbor validity check."""
        if self.role in [Roles.ROOT, Roles.UNDISCOVERED]:
            return  # Root has no parent, undiscovered doesn't care yet
        
        if self.parent_gui is None:
            return
        
        # Use existing neighbor validity system
        parent_status = self.get_neighbor_status(self.parent_gui)
        
        if parent_status is None:
            # Parent not in neighbor table at all - shouldn't happen but handle it
            self.log(f"WARNING: Parent {self.parent_gui} not in neighbor table!")
            self.handle_parent_failure()
            return
        
        if not parent_status['valid']:
            # Parent has timed out according to NEIGHBOR_VALIDITY_TIMEOUT
            time_since_heard = self.now - parent_status['last_heard']
            self.log(f"PARENT TIMEOUT! No heartbeat from parent {self.parent_gui} for {time_since_heard:.1f} time units")
            self.handle_parent_failure()

    def handle_parent_failure(self):
        """Handle the case where parent node has failed/left network."""
        self.log(f"Parent {self.parent_gui} has failed. Orphaning node {self.id}")
        
        # If this node is a router, check if it should demote
        if self.role == Roles.ROUTER:
            # Router only exists to forward for children
            # If parent is dead, router should leave too
            if len(self.members_table) == 0:
                self.log(f"Router {self.id} has no children and parent died. Leaving network.")
                self.orphan_and_notify_children()
                return
        
        # Notify all children that they're orphaned
        self.orphan_and_notify_children()

    def orphan_and_notify_children(self):
        """Orphan this node and IMMEDIATELY notify all children to orphan as well."""
        self.log(f"Node {self.id} orphaning and notifying {len(self.members_table)} children")
        
        # Send ORPHAN notification to all direct children in members_table
        for child_gui in list(self.members_table):
            child_addr = self.neighbors_table.get(child_gui, {}).get('addr')
            if child_addr:
                self.send({
                    'dest': child_addr,
                    'type': 'ORPHAN_NOTIFICATION',
                    'source': self.addr if self.addr else None,
                    'gui': self.id,
                    'creation_time': self.now
                })
                self.log(f"  -> Sent ORPHAN to child {child_gui}")
        
        # NEW: Directly orphan parent if it's a router
        if self.parent_gui is not None:
            # Find the actual parent node object
            for node in sim.nodes:
                if node.id == self.parent_gui:
                    if hasattr(node, 'role') and node.role == Roles.ROUTER:
                        self.log(f"  -> Parent {self.parent_gui} is ROUTER - directly orphaning it")
                        # Remove self from parent's member list
                        if self.id in node.members_table:
                            node.members_table.remove(self.id)
                        # If router has no children left, orphan it
                        if len(node.members_table) == 0:
                            node.log(f"ROUTER has no children left - orphaning")
                            node.orphan_and_notify_children()  # Recursive cascade upward
                    break
        
        # Orphan self immediately after notifications
        self.become_orphaned()

    def become_orphaned(self):
        """Become orphaned and rejoin network."""
        self.log(f"Node {self.id} becoming orphaned")
        
        # If this was a cluster head, it loses that status
        if self.role == Roles.CLUSTER_HEAD:
            self.log(f"Cluster Head {self.id} lost parent, demoting")
        
        if self.role == Roles.ROUTER:
            self.log(f"Router {self.id} lost parent, demoting")
        
        # Reset to unregistered state and attempt to rejoin
        self.become_unregistered()

    ###################
    def select_and_join(self):
        min_hop = 99999
        min_hop_gui = 99999

        non_router_candidates = []
        for gui in self.candidate_parents_table:
            neighbor = self.neighbors_table.get(gui)
            if neighbor and neighbor.get('role') != Roles.ROUTER:
                non_router_candidates.append(gui)

        candidates = non_router_candidates if non_router_candidates else self.candidate_parents_table
        
        for gui in candidates:
            neighbor = self.neighbors_table[gui]
            if neighbor['hop_count'] < min_hop or \
            (neighbor['hop_count'] == min_hop and gui < min_hop_gui):
                min_hop = neighbor['hop_count']
                min_hop_gui = gui
        
        selected_addr = self.neighbors_table[min_hop_gui]['source']
        self.send_join_request(selected_addr)
        self.set_timer('TIMER_JOIN_REQUEST', 5)


    ###################
    def send_probe(self):
        """Sending probe message to be discovered and registered.

        Args:

        Returns:

        """
        self.send({'dest': wsn.BROADCAST_ADDR, 'gui': self.id,'type': 'PROBE', 'creation_time': self.now})

    ###################
    def send_heart_beat(self):
        """Sending heart beat message

        Args:

        Returns:

        """
        one_hop_neighbors = [
            gui for gui, data in self.neighbors_table.items()
            if data.get('next_hop') is None
        ] 
        self.send({'dest': wsn.BROADCAST_ADDR,
                   'type': 'HEART_BEAT',
                   'source': self.ch_addr if self.ch_addr is not None else self.addr,
                   'gui': self.id,
                   'role': self.role,
                   'addr': self.addr,
                   'ch_addr': self.ch_addr,
                   'hop_count': self.hop_count,
                   'neighbors': one_hop_neighbors,
                   'creation_time': self.now})

    ###################
    def send_join_request(self, dest):
        """Sending join request message to given destination address to join destination network

        Args:
            dest (Addr): Address of destination node
        Returns:

        """
        self.send({'dest': dest, 'type': 'JOIN_REQUEST', 'gui': self.id, 'creation_time': self.now})

    ###################
    def send_join_reply(self, gui, addr):
        """Sending join reply message to register the node requested to join.
        The message includes a gui to determine which node will take this reply, an addr to be assigned to the node
        and a root_addr.

        Args:
            gui (int): Global unique ID
            addr (Addr): Address that will be assigned to new registered node
        Returns:

        """
        self.send({'dest': wsn.BROADCAST_ADDR, 'type': 'JOIN_REPLY', 'source': self.ch_addr,
                   'gui': self.id, 'dest_gui': gui, 'addr': addr, 'root_addr': self.root_addr,
                   'hop_count': self.hop_count+1, 'creation_time': self.now})

    ###################
    def send_join_ack(self, dest):
        """Sending join acknowledgement message to given destination address.

        Args:
            dest (Addr): Address of destination node
        Returns:

        """
        self.send({'dest': dest, 'type': 'JOIN_ACK', 'source': self.addr,
                   'gui': self.id, 'creation_time': self.now})

    def print_all_neighbor_tables(self):
        """Print neighbor tables for ALL nodes in the simulation"""
        print("\n" + "="*70)
        print("NEIGHBOR TABLES FOR ALL NODES")
        print("="*70)
        
        for node in sim.nodes:
            if not hasattr(node, 'neighbors_table'):
                continue
                
            print(f"\nNode {node.id} Neighbor Table:")
            
            if not node.neighbors_table:
                print("  (empty)")
                continue
            
            one_hop = []
            two_hop = []
            
            for neighbor_id, info in node.neighbors_table.items():
                next_hop = info.get('next_hop')
                
                if next_hop is None:
                    # Direct 1-hop neighbor
                    one_hop.append(neighbor_id)
                else:
                    # 2-hop neighbor
                    two_hop.append((neighbor_id, next_hop))
            
            # Print 1-hop neighbors
            if one_hop:
                one_hop.sort()
                print(f"  1-hop: {one_hop}")
            
            # Print 2-hop neighbors
            if two_hop:
                two_hop.sort()
                print(f"  2-hop: ", end="")
                for dest, via in two_hop:
                    print(f"{dest}(via {via}) ", end="")
                print() 
            
            if not one_hop and not two_hop:
                print("  (no valid neighbors)")
        
        print("="*70 + "\n")

    ###################
    def route_and_forward_package(self, pck):
        """Hybrid routing: neighbor table first (for data), then hierarchical tree routing"""
        dest_addr = pck['dest']
        dest_id = dest_addr.node_addr
        is_test = pck.get('type') == 'TEST_MESSAGE'
        
        # Check Loops
        if 'visited_nodes' not in pck:
            pck['visited_nodes'] = []
        
        if self.id in pck['visited_nodes']:
            if is_test:
                print(f"Unexpected loop at Node {self.id}! Path: {pck['path_info']['path']}")
            return 
        
        pck['visited_nodes'].append(self.id)
        
        #Mesh Routing
        if is_test and dest_id in self.neighbors_table:
            neighbor_info = self.neighbors_table[dest_id]
            neighbor_addr = neighbor_info.get('addr')
            time_since_heard = self.now - neighbor_info['last_heard']
            
            if (time_since_heard <= NEIGHBOR_VALIDITY_TIMEOUT and 
                neighbor_addr is not None and 
                neighbor_addr == dest_addr):
                
                next_hop_gui = neighbor_info.get('next_hop')
                
                # Direct 1-hop neighbor (next_hop is None)
                if next_hop_gui is None:
                    # Send directly to destination
                    pck['next_hop'] = dest_addr
                    pck['path_info']['routing_method'].append('mesh-1hop')
                    self.send(pck)
                    return
                            
                # 2-hop neighbor via intermediate
                else:
                    intermediate_info = self.neighbors_table.get(next_hop_gui)
                    if intermediate_info is not None:
                        intermediate_addr = intermediate_info.get('addr')
                        intermediate_time = self.now - intermediate_info.get('last_heard', float('inf'))
                        
                        if (intermediate_addr is not None and 
                            intermediate_time <= NEIGHBOR_VALIDITY_TIMEOUT):
                            pck['next_hop'] = intermediate_addr
                            pck['path_info']['routing_method'].append('mesh-2hop')
                            self.send(pck)
                            return
        
        # TREE ROUTING - Check children FIRST, then self, then parent
        if is_test:
            pck['path_info']['routing_method'].append('tree')
        
        # Check if destination is down the tree
        for child_gui, child_data in self.child_networks_table.items():
            networks = child_data.get('networks', []) if isinstance(child_data, dict) else child_data
            if dest_addr.net_addr in networks:
                child_addr = self.neighbors_table.get(child_gui, {}).get('addr')
                if child_addr is not None:
                    pck['next_hop'] = child_addr
                    self.send(pck)
                    return
        
        if self.ch_addr is not None and dest_addr.net_addr == self.ch_addr.net_addr:
            pck['next_hop'] = dest_addr
            self.send(pck)
            return
        
        # Not in subtree - route to parent
        if self.role != Roles.ROOT and self.parent_gui is not None:
            parent_addr = self.neighbors_table.get(self.parent_gui, {}).get('ch_addr')
            if parent_addr is not None:
                pck['next_hop'] = parent_addr
                self.send(pck)
                return
        
        # No route found
        if is_test:
            if self.role == Roles.ROOT:
                print(f"ROOT: No route to {dest_addr}")
            else:
                print(f"Node {self.id}: No route to {dest_addr}")

    ###################
    def send_network_request(self):
        """Sending network request message to root address to be cluster head

        Args:

        Returns:

        """
        self.route_and_forward_package({'dest': self.root_addr, 'type': 'NETWORK_REQUEST', 'source': self.addr, 'creation_time': self.now})

    ###################
    def send_network_reply(self, dest, addr):
        """Sending network reply message to dest address to be cluster head with a new adress

        Args:
            dest (Addr): destination address
            addr (Addr): cluster head address of new network

        Returns:

        """
        self.route_and_forward_package({'dest': dest, 'type': 'NETWORK_REPLY', 'source': self.addr, 'addr': addr, 'creation_time': self.now})

    ###################
    
    def send_network_update(self):
        """Sending network update message to parent with hierarchical CH structure"""
        child_networks = [self.ch_addr.net_addr] if self.ch_addr else []
        for child_gui, child_data in self.child_networks_table.items():
            if isinstance(child_data, dict):
                child_networks.extend(child_data.get('networks', []))
            else:
                child_networks.extend(child_data)
        

        all_child_chs = []
        if self.role == Roles.CLUSTER_HEAD and self.ch_addr is not None:
            all_child_chs.append(self.id)
        
        for child_gui, child_data in self.child_networks_table.items():
            if isinstance(child_data, dict):
                all_child_chs.extend(child_data.get('chs', []))

        self.send({
            'dest': self.neighbors_table[self.parent_gui]['ch_addr'], 
            'type': 'NETWORK_UPDATE', 
            'source': self.addr,
            'gui': self.id, 
            'child_networks': child_networks, 
            'child_chs': all_child_chs,
            'creation_time': self.now  
        })

    def send_test_message(self, dest_id, message_content):
        """Send a test message to another node by ID"""
        dest_node = None
        for node in sim.nodes:
            if node.id == dest_id:
                dest_node = node
                break
        
        if dest_node is None or dest_node.addr is None:
            print(f"Cannot send from Node {self.id} to Node {dest_id}: Destination not found or not registered")
            return
        
        print(f"\n[Testing: Node {self.id} -> Node {dest_id}] ", end='')

        self.route_and_forward_package({
            'dest': dest_node.addr,
            'type': 'TEST_MESSAGE',
            'source': self.addr,
            'content': message_content,
            'path_info': {
                'origin_id': self.id,
                'dest_id': dest_id,
                'path': [self.id],
                'routing_method': ['START']
            },
            'creation_time': self.now
        })

    def send_ch_leave_command(self, target_ch_gui):
        """Tell another CH to leave the network."""
        target_addr = self.neighbors_table.get(target_ch_gui, {}).get('addr')
        if target_addr:
            self.log(f"CH {self.id} sending LEAVE command to CH {target_ch_gui}")
            self.send({
                'dest': target_addr,
                'type': 'CH_LEAVE_COMMAND',
                'gui': self.id,
                'creation_time': self.now
        })

    ###################
    def on_receive(self, pck):
        """Executes when a package received."""

        if 'creation_time' in pck:
            delay = self.now - pck['creation_time']
            PACKET_LOGS.append({
                'type': pck['type'],
                'source': pck.get('gui', 'unknown'),
                'dest': self.id,
                'creation_time': pck['creation_time'],
                'arrival_time': self.now,
                'delay': delay
            })
        
        if pck['type'] == 'ORPHAN_NOTIFICATION':
            if pck['gui'] == self.parent_gui:
                self.log(f"!!! ORPHAN notification from parent {self.parent_gui} - cascading immediately")
                self.orphan_and_notify_children()
            return

        if pck['type'] == 'TEST_MESSAGE':
            if 'path_info' in pck:
                pck['path_info']['path'].append(self.id)            
            
            if self.addr is not None and pck['dest'] == self.addr:
                print(f"Node {self.id} ARRIVED")
                path_info = pck.get('path_info', {})
                path = path_info.get('path', [])
                methods = path_info.get('routing_method', [])
                origin_id = path_info.get('origin_id', '?')
                dest_id = path_info.get('dest_id', '?')
                
                path_str = str(path[0])
                for i in range(1, len(path)):
                    method = methods[i] if i < len(methods) else 'unknown'
                    routing_type = 'mesh' if 'neighbor' in method else 'tree'
                    path_str += f" -({routing_type})-> {path[i]}"
                return 
                
            else:
                print(f"Node {self.id} -> ", end='')
                self.route_and_forward_package(pck)
                return  

        if self.role == Roles.ROOT or self.role == Roles.CLUSTER_HEAD:
            if 'next_hop' in pck.keys() and pck['dest'] != self.addr and pck['dest'] != self.ch_addr:
                self.route_and_forward_package(pck)
                return
            
            if pck['type'] == 'CH_LEAVE_COMMAND':
                if self.role == Roles.CLUSTER_HEAD:
                    sender_gui = pck['gui']
                    self.log(f"CH {self.id} received LEAVE command from CH {sender_gui} - leaving network")
                    self.orphan_and_notify_children()
                return

            if pck['type'] == 'HEART_BEAT':
                self.update_neighbor(pck)
    
                if self.role == Roles.CLUSTER_HEAD:
                    sender_role = pck.get('role')
                    sender_gui = pck['gui']
                    
                    # Ignore collision if sender is our child or being promoted by us
                    if sender_gui in self.members_table or sender_gui in self.pending_promotions:
                        # This is our child/promoted node, ignore collision
                        pass
                    elif sender_role in [Roles.CLUSTER_HEAD, Roles.ROOT]:
                        # Track how many times we've heard from this CH/ROOT
                        if sender_gui not in self.ch_collision_count:
                            self.ch_collision_count[sender_gui] = 0
                        
                        self.ch_collision_count[sender_gui] += 1
                        
                        if self.ch_collision_count[sender_gui] >= self.ch_collision_threshold:
                            # NEW: Instead of leaving immediately, start random timer
                            if sender_gui not in self.ch_collision_timers:
                                random_delay = random.uniform(0, 50)
                                self.log(f"CH {self.id} heard {self.ch_collision_count[sender_gui]} heartbeats from {sender_role.name} {sender_gui} - timer set for {random_delay:.1f}s")
                                self.ch_collision_timers[sender_gui] = True
                                self.set_timer('TIMER_CH_COLLISION_DECISION', random_delay, other_ch_gui=sender_gui)
                        else:
                            self.log(f"CH {self.id} heard heartbeat #{self.ch_collision_count[sender_gui]} from {sender_role.name} {sender_gui}")
                                        
                sender = pck['gui']

                if sender in self.pending_promotions:
                    addr = self.neighbors_table[sender]['addr']
                    promote_packet = {
                        'type': 'PROMOTE_TO_CH',
                        'dest': addr
                    }
                    self.send(promote_packet)
                    self.pending_promotions.remove(sender)
                    if (self.changeRole):
                        self.set_role(Roles.ROUTER)

            if pck['type'] == 'PROBE':
                self.send_heart_beat()
            if pck['type'] == 'JOIN_REQUEST':
                self.send_join_reply(pck['gui'], wsn.Addr(self.ch_addr.net_addr, pck['gui']))
            if pck['type'] == 'NETWORK_REQUEST':
                if self.role == Roles.ROOT:
                    new_addr = wsn.Addr(pck['source'].node_addr,254)
                    self.send_network_reply(pck['source'],new_addr)
            if pck['type'] == 'JOIN_ACK':
                self.members_table.append(pck['gui'])
            if pck['type'] == 'NETWORK_UPDATE':
                self.child_networks_table[pck['gui']] = {
                    'networks': pck['child_networks'],
                    'chs': pck.get('child_chs', [])
                }
                
                if self.role == Roles.ROOT:
                    print(f"\n[Root] child_networks_table[{pck['gui']}]:")
                    print(f"  Networks: {pck['child_networks']}")
                    print(f"  CHs: {pck.get('child_chs', [])}")
                
                if self.role != Roles.ROOT:
                    self.send_network_update()
        
        elif self.role == Roles.ROUTER:
            if 'next_hop' in pck.keys() and pck['dest'] != self.addr and pck['dest'] != self.ch_addr:
                self.route_and_forward_package(pck)
                return
            
            if pck['type'] == 'HEART_BEAT':
                self.update_neighbor(pck)
                sender = pck['gui']
        
                # NEW: Check if parent is also a router - LEAVE immediately
                if sender == self.parent_gui:
                    sender_role = pck.get('role')
                    if sender_role == Roles.ROUTER:
                        self.log(f"ROUTER {self.id} detected parent {self.parent_gui} is also ROUTER - leaving network")
                        self.orphan_and_notify_children()
                        return  # Stop processing
                
                if sender in self.pending_promotions:
                    if sender in self.neighbors_table:
                        addr = self.neighbors_table[sender].get('addr')
                        if addr is not None:
                            promote_packet = {
                                'type': 'PROMOTE_TO_CH',
                                'dest': addr
                            }
                            self.send(promote_packet)
                            self.pending_promotions.remove(sender)
                        else:
                            self.pending_promotions.remove(sender)
                    else:
                        self.pending_promotions.remove(sender)
                    
                    if pck['type'] == 'JOIN_REQUEST':
                        sender_gui = pck['gui']
                        if sender_gui in self.neighbors_table:
                            if self.ch_addr is not None:
                                self.send_join_reply(sender_gui, wsn.Addr(self.ch_addr.net_addr, sender_gui))
                            else:
                                self.route_and_forward_package(pck)
                        else:
                            self.route_and_forward_package(pck)
            
            if pck['type'] == 'JOIN_ACK':
                self.members_table.append(pck['gui'])
            
            if pck['type'] == 'NETWORK_REQUEST':
                self.route_and_forward_package(pck)
            
            if pck['type'] == 'NETWORK_REPLY':
                self.route_and_forward_package(pck)
            
            if pck['type'] == 'NETWORK_UPDATE':
                self.child_networks_table[pck['gui']] = {
                    'networks': pck['child_networks'],
                    'chs': pck.get('child_chs', [])
                }
                
                if self.parent_gui is not None:
                    self.send_network_update()

        elif self.role == Roles.REGISTERED:
            if pck['type'] == 'HEART_BEAT':
                self.update_neighbor(pck)

            if pck['type'] == 'PROBE':
                sender = pck['gui']
                if (sender not in self.received_probes):
                    self.received_probes[sender] = 1
                elif (self.received_probes[sender] < 3):
                    self.received_probes[sender] += 1
                if (self.received_probes[sender] >= 3):
                    if self.can_promote:
                        self.becomeRouter = True
                        self.send_heart_beat()
                
            if pck['type'] == 'JOIN_REQUEST':
                if self.can_promote:
                    self.received_JR_guis.append(pck['gui'])
                    self.send_network_request()
            if pck['type'] == 'NETWORK_REPLY':
                self.set_role(Roles.CLUSTER_HEAD)
                try:
                    write_clusterhead_distances_csv("clusterhead_distances.csv")
                except Exception as e:
                    self.log(f"CH CSV export error: {e}")
                self.scene.nodecolor(self.id, 0, 0, 1)
                self.ch_addr = pck['addr']
                self.send_network_update()
                self.send_heart_beat()
                for gui in self.received_JR_guis:
                    self.send_join_reply(gui, wsn.Addr(self.ch_addr.net_addr,gui))
                    self.pending_promotions.add(gui)

            if pck['type'] == 'PROMOTE_TO_CH':
                self.send_network_request()
                self.changeRole = False

        elif self.role == Roles.UNDISCOVERED:
            if pck['type'] == 'HEART_BEAT':
                self.update_neighbor(pck)
                self.become_unregistered()

        if self.role == Roles.UNREGISTERED:
            if pck['type'] == 'HEART_BEAT':
                self.update_neighbor(pck)
            if pck['type'] == 'JOIN_REPLY':
                self.kill_timer('TIMER_PROBE')
                if pck['dest_gui'] == self.id:
                    # Record join time
                    if self.probe_start_time:
                        join_delay = self.now - self.probe_start_time
                        JOIN_TIMES.append({
                            'node_id': self.id,
                            'join_delay': join_delay
                        })
                    
                    self.addr = pck['addr']
                    self.parent_gui = pck['gui']
                    self.root_addr = pck['root_addr']
                    self.hop_count = pck['hop_count']
                    self.draw_parent()
                    self.kill_timer('TIMER_JOIN_REQUEST')
                    self.send_heart_beat()
                    self.set_timer('TIMER_HEART_BEAT', config.HEARTH_BEAT_TIME_INTERVAL)
                    self.send_join_ack(pck['source'])
                    
                    if self.ch_addr is not None:
                        self.set_role(Roles.CLUSTER_HEAD)
                        self.send_network_update()
                        self.can_promote = True
                    else:
                        self.set_role(Roles.REGISTERED)
                        # REGISTERED nodes must wait before they can promote to
                        self.can_promote = False
                        self.set_timer('TIMER_PROMOTION_COOLDOWN', 10) 
                        # # sensor implementation
                        # timer_duration =  self.id % 20
                        # if timer_duration == 0: timer_duration = 1
                        # self.set_timer('TIMER_SENSOR', timer_duration)

    def kill_node(self):
        """Manually kill this node, triggering orphaning of children."""
        self.log(f"Node {self.id} is being killed/powered off")
        self.orphan_and_notify_children()
        self.sleep()
        self.kill_all_timers()
        self.scene.nodecolor(self.id, 0.5, 0.5, 0.5)

    ###################
    def on_timer_fired(self, name, *args, **kwargs):
        """Executes when a timer fired.

        Args:
            name (string): Name of timer.
            *args (string): Additional args.
            **kwargs (string): Additional key word args.
        Returns:

        """
        if name == 'TIMER_ARRIVAL':
            self.scene.nodecolor(self.id, 1, 0, 0)
            self.wake_up()
            self.probe_start_time = self.now
            self.set_timer('TIMER_PROBE', 1)

        elif name == 'TIMER_PROBE':  # it sends probe if counter didn't reach the threshold once timer probe fired.
            if self.c_probe < self.th_probe:
                self.send_probe()
                self.c_probe += 1
                self.set_timer('TIMER_PROBE', 1)
            else:  # if the counter reached the threshold
                if self.is_root_eligible:  # if the node is root eligible, it becomes root
                    self.set_role(Roles.ROOT)
                    self.scene.nodecolor(self.id, 0, 0, 0)
                    self.addr = wsn.Addr(self.id, 254)
                    self.ch_addr = wsn.Addr(self.id, 254)
                    self.root_addr = self.addr
                    self.hop_count = 0
                    self.set_timer('TIMER_HEART_BEAT', config.HEARTH_BEAT_TIME_INTERVAL)
                    self.set_timer('TIMER_RUN_TESTS', config.SIM_DURATION / 4)
                else:  # otherwise it keeps trying to sending probe after a long time
                    self.c_probe = 0
                    self.set_timer('TIMER_PROBE', 30)

        elif name == 'TIMER_HEART_BEAT':  # it sends heart beat message once heart beat timer fired
            self.send_heart_beat()
            self.set_timer('TIMER_HEART_BEAT', config.HEARTH_BEAT_TIME_INTERVAL)
            if self.role not in [Roles.ROOT, Roles.UNDISCOVERED]:
                self.check_parent_alive()
            #print(self.id)

        elif name == 'TIMER_JOIN_REQUEST':  # if it has not received heart beat messages before, it sets timer again and wait heart beat messages once join request timer fired.
            if len(self.candidate_parents_table) == 0:
                self.become_unregistered()
            else:  # otherwise it chose one of them and sends join request
                self.select_and_join()

        elif name == 'TIMER_REJOIN_DELAY':
            self.log(f"Node {self.id} starting rejoin process after delay")
            self.send_probe()
            self.set_timer('TIMER_JOIN_REQUEST', 20)

        elif name == 'TIMER_CH_COLLISION_DECISION':
            other_ch_gui = kwargs.get('other_ch_gui')
            
            # Check if we're still a CH and still hearing from the other CH
            if self.role == Roles.CLUSTER_HEAD and other_ch_gui in self.ch_collision_timers:
                self.log(f"CH {self.id} timer expired - telling CH {other_ch_gui} to leave")
                self.send_ch_leave_command(other_ch_gui)
                
                # Clean up
                self.ch_collision_timers.pop(other_ch_gui, None)
                self.ch_collision_count.pop(other_ch_gui, None)

        elif name == 'TIMER_SENSOR':
            self.route_and_forward_package({'dest': self.root_addr, 'type': 'SENSOR', 'source': self.addr, 'sensor_value': random.uniform(10,50)})
            timer_duration =  self.id % 20
            if timer_duration == 0: timer_duration = 1
            self.set_timer('TIMER_SENSOR', timer_duration)
        elif name == 'TIMER_EXPORT_CH_CSV':
            # Only root should drive exports (cheap guard)
            if self.role == Roles.ROOT:
                write_clusterhead_distances_csv("clusterhead_distances.csv")
                # reschedule
                self.set_timer('TIMER_EXPORT_CH_CSV', config.EXPORT_CH_CSV_INTERVAL)
        elif name == 'TIMER_EXPORT_NEIGHBOR_CSV':
            if self.role == Roles.ROOT:
                write_neighbor_distances_csv("neighbor_distances.csv")
                self.set_timer('TIMER_EXPORT_NEIGHBOR_CSV', config.EXPORT_NEIGHBOR_CSV_INTERVAL)

        elif name == 'TIMER_RUN_TESTS':
            if self.role == Roles.ROOT:
                # Open file for all test output
                self.test_output_file = open("routing_tests_and_tables.txt", "w")
                
                import sys
                original_stdout = sys.stdout
                sys.stdout = self.test_output_file  # Redirect all print statements to file
                
                print("\n" + "="*60)
                print(f"ROUTING TEST - Running at time {self.now}")
                print("="*60)
                
                registered_nodes = []
                for node in sim.nodes:
                    if hasattr(node, 'addr') and node.addr is not None:
                        registered_nodes.append(node)
                
                if len(registered_nodes) < 2:
                    print("Error: Need at least 2 registered nodes")
                    sys.stdout = original_stdout
                    self.test_output_file.close()
                    return
                
                # Build test queue
                self.test_queue = []
                for source_node in registered_nodes:
                    for dest_node in registered_nodes:
                        if source_node.id == dest_node.id:
                            continue
                        self.test_queue.append((source_node, dest_node.id))
                
                total_tests = len(self.test_queue)
                print(f"\nFound {len(registered_nodes)} registered nodes")
                print(f"Testing all {total_tests} routes sequentially...")
                print("="*60)
                
                # Don't restore stdout yet - keep writing to file
                sys.stdout = original_stdout  # Restore temporarily for console feedback
                print(f"Starting {total_tests} tests - writing to routing_tests_and_tables.txt")
                sys.stdout = self.test_output_file  # Back to file
                
                # Start the first test
                self.test_index = 0
                self.set_timer('TIMER_NEXT_TEST', 0.1)

        elif name == 'TIMER_NEXT_TEST':
            if self.role == Roles.ROOT and self.test_index < len(self.test_queue):
                source_node, dest_id = self.test_queue[self.test_index]
                self.test_index += 1
                
                source_node.send_test_message(dest_id, f"Test #{self.test_index}")
                
                # Schedule next test after a short delay
                if self.test_index < len(self.test_queue):
                    self.set_timer('TIMER_NEXT_TEST', 0.5)
                else:
                    import sys
                    
                    # Still writing to file
                    print(f"\n{'='*60}")
                    print(f"All {len(self.test_queue)} test messages completed at time {self.now}!")
                    print(f"{'='*60}\n")
                    
                    # Print neighbor tables to file
                    self.print_all_neighbor_tables()
                    
                    # Close file and restore stdout
                    self.test_output_file.close()
                    
                    # Print confirmation to console
                    sys.stdout = sys.__stdout__  # Restore to original stdout
                    print(f"\nAll tests complete! Results saved to routing_tests_and_tables.txt")

                    for node in sim.nodes:
                        if node.id == 15:
                            print(f"\nKilling node {node.id} to test orphaning...")
                            node.kill_node()
                            break

        elif name == 'TIMER_PROMOTION_COOLDOWN':
            self.can_promote = True
    

ROOT_ID = random.randrange(config.SIM_NODE_COUNT)  # 0..count-1



def write_node_distances_csv(path="node_distances.csv"):
    """Write pairwise node-to-node Euclidean distances as an edge list."""
    ids = sorted(NODE_POS.keys())
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["source_id", "target_id", "distance"])
        for i, sid in enumerate(ids):
            x1, y1 = NODE_POS[sid]
            for tid in ids[i+1:]:  # i+1 to avoid duplicates and self-pairs
                x2, y2 = NODE_POS[tid]
                dist = math.hypot(x1 - x2, y1 - y2)
                w.writerow([sid, tid, f"{dist:.6f}"])


def write_node_distance_matrix_csv(path="node_distance_matrix.csv"):
    ids = sorted(NODE_POS.keys())
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["node_id"] + ids)
        for sid in ids:
            x1, y1 = NODE_POS[sid]
            row = [sid]
            for tid in ids:
                x2, y2 = NODE_POS[tid]
                dist = math.hypot(x1 - x2, y1 - y2)
                row.append(f"{dist:.6f}")
            w.writerow(row)


def write_clusterhead_distances_csv(path="clusterhead_distances.csv"):
    """Write pairwise distances between current cluster heads."""
    clusterheads = []
    for node in sim.nodes:
        # Only collect nodes that are cluster heads and have recorded positions
        if hasattr(node, "role") and node.role == Roles.CLUSTER_HEAD and node.id in NODE_POS:
            x, y = NODE_POS[node.id]
            clusterheads.append((node.id, x, y))

    if len(clusterheads) < 2:
        # Still write the header so the file exists/is refreshed
        with open(path, "w", newline="") as f:
            csv.writer(f).writerow(["clusterhead_1", "clusterhead_2", "distance"])
        return

    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["clusterhead_1", "clusterhead_2", "distance"])
        for i, (id1, x1, y1) in enumerate(clusterheads):
            for id2, x2, y2 in clusterheads[i+1:]:
                dist = math.hypot(x1 - x2, y1 - y2)
                w.writerow([id1, id2, f"{dist:.6f}"])



def write_neighbor_distances_csv(path="neighbor_distances.csv", dedupe_undirected=True):
    """
    Export neighbor distances per node.
    Each row is (node -> neighbor) with distance from NODE_POS.

    Args:
        path (str): output CSV path
        dedupe_undirected (bool): if True, writes each unordered pair once
                                  (min(node_id,neighbor_id), max(...)).
                                  If False, writes one row per direction.
    """
    # Safety: ensure we can compute distances
    if not globals().get("NODE_POS"):
        raise RuntimeError("NODE_POS is missing; record positions during create_network().")

    # Prepare a set to avoid duplicates if dedupe_undirected=True
    seen_pairs = set()

    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["node_id", "neighbor_id", "distance",
                    "neighbor_role", "neighbor_hop_count", "arrival_time"])

        for node in sim.nodes:
            # Skip nodes without any neighbor info yet
            if not hasattr(node, "neighbors_table"):
                continue

            x1, y1 = NODE_POS.get(node.id, (None, None))
            if x1 is None:
                continue 

            # neighbors_table: key = neighbor GUI, value = heartbeat packet dict
            for n_gui, pck in getattr(node, "neighbors_table", {}).items():
                # Optional dedupe (unordered)
                if dedupe_undirected:
                    key = (min(node.id, n_gui), max(node.id, n_gui))
                    if key in seen_pairs:
                        continue
                    seen_pairs.add(key)

                # Position of neighbor
                x2, y2 = NODE_POS.get(n_gui, (None, None))
                if x2 is None:
                    continue

                # Distance (prefer pck['distance'] if you added it in update_neighbor)
                dist = pck.get("distance")
                if dist is None:
                    dist = math.hypot(x1 - x2, y1 - y2)

                # Extra fields (best-effort; may be missing)
                n_role = getattr(pck.get("role", None), "name", pck.get("role", None))
                hop = pck.get("hop_count", "")
                at  = pck.get("arrival_time", "")

                w.writerow([node.id, n_gui, f"{dist:.6f}", n_role, hop, at])

###########################################################
def create_network(node_class, number_of_nodes=100):
    """Creates given number of nodes at random positions with random arrival times.

    Args:
        node_class (Class): Node class to be created.
        number_of_nodes (int): Number of nodes.
    Returns:

    """
    edge = math.ceil(math.sqrt(number_of_nodes))
    for i in range(number_of_nodes):
        x = i / edge
        y = i % edge
        px = 300 + config.SCALE*x * config.SIM_NODE_PLACING_CELL_SIZE + random.uniform(-1 * config.SIM_NODE_PLACING_CELL_SIZE / 3, config.SIM_NODE_PLACING_CELL_SIZE / 3)
        py = 200 + config.SCALE* y * config.SIM_NODE_PLACING_CELL_SIZE + random.uniform(-1 * config.SIM_NODE_PLACING_CELL_SIZE / 3, config.SIM_NODE_PLACING_CELL_SIZE / 3)
        node = sim.add_node(node_class, (px, py))
        NODE_POS[node.id] = (px, py)  
        node.tx_range = config.NODE_TX_RANGE * config.SCALE
        node.logging = True
        node.arrival = random.uniform(0, config.NODE_ARRIVAL_MAX)
        if node.id == ROOT_ID:
            node.arrival = 0.1


sim = wsn.Simulator(
    duration=config.SIM_DURATION,
    timescale=config.SIM_TIME_SCALE,
    visual=config.SIM_VISUALIZATION,
    terrain_size=config.SIM_TERRAIN_SIZE,
    title=config.SIM_TITLE)

# creating random network
create_network(SensorNode, config.SIM_NODE_COUNT)

write_node_distances_csv("node_distances.csv")
write_node_distance_matrix_csv("node_distance_matrix.csv")



# start the simulation
sim.run()
print("Simulation Finished")

import time
time.sleep(1)




# Export packet delays
with open("packet_delays.csv", "w") as f:
    f.write("packet_type,source,dest,creation_time,arrival_time,delay_ms\n")
    for log in PACKET_LOGS:
        f.write(f"{log['type']},{log['source']},{log['dest']},{log['creation_time']:.3f},{log['arrival_time']:.3f},{log['delay']:.3f}\n")

# Export join times
with open("join_times.csv", "w") as f:
    f.write("node_id,join_delay_ms\n")
    for jt in JOIN_TIMES:
        f.write(f"{jt['node_id']},{jt['join_delay']:.3f}\n")

# Print summary
if JOIN_TIMES:
    avg_join = sum(j['join_delay'] for j in JOIN_TIMES) / len(JOIN_TIMES)
    print(f"\nAverage Join Time: {avg_join:.3f} ms")

if PACKET_LOGS:
    avg_delay = sum(p['delay'] for p in PACKET_LOGS) / len(PACKET_LOGS)
    print(f"Average Packet Delay: {avg_delay:.3f} ms")
    print(f"Total Packets Logged: {len(PACKET_LOGS)}")

#test_all_registered_nodes()

# Created 100 nodes at random locations with random arrival times.
# When nodes are created they appear in white
# Activated nodes becomes red
# Discovered nodes will be yellow
# Registered nodes will be green.
# Root node will be black.
# Routers/Cluster Heads should be blue