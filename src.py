from slackclient import SlackClient
from graph_tool.all import *
from numpy import intersect1d
from matplotlib.colors import to_hex

slack = SlackClient('SECRETAPIKEY')

graph_changes_message = ""                            # The title of the generated graph file, if uploaded to Slack.
ts = 1529919747.6                                     # A reference timestamp, used to scale the channel activity color filter.
dev_channel = "YOURDEVCHANNELID"                      # The ID of the channel to which you would like to upload any generated files.
min_shared = 7                                        # The minimum number of shared users required to create an edge between channels.

# Initializes the channel graph and weights. 
def init_channelweb():

        response = slack.api_call("channels.list")
        channelslist = response['channels']
        g = Graph(directed=False)
        channel_names = g.new_vertex_property("string")
        channel_users = g.new_vertex_property("vector<string>")
        channel_ids = g.new_vertex_property("string")
        num_users = g.new_vertex_property("int")
        
        # Initialize channels. Does not include archived channels (with zero users).
        for curchannel in channelslist:
                v =  g.add_vertex()
                channel_names[v] = curchannel['name']
                id = curchannel['id']
                channel_ids[v] = id
                                channeldata = slack.api_call("channels.info", channel=id)
                channel_users[v] = channeldata['channel']['members']
                num_users[v] = len(channel_users[v])
                if len(channel_users[v]) < 1:
                        g.remove_vertex(v)

        scaled_shared_users = g.new_edge_property("float")
        raw_shared_users = g.new_edge_property("int")
        for v1 in g.vertices():
                for v2 in g.vertices():
                        users1 = channel_users[v1]
                        users2 = channel_users[v2]
                        shared_users = len(intersect1d(users1, users2))
                        if (v1 != v2) and (shared_users > MIN_SHARED):
                                e = g.edge(v1, v2, add_missing=True)
                                raw_shared_users[e] = min(shared_users, 50)
                                total_users = len(users1) + len(users2)
                                scaled_users = 1.000 * shared_users / min(len(users1), len(users2))
                                scaled_shared_users[e] = scaled_users
                                
        # Store graph properties as internal in order to bundle into .gt file.
        g.vertex_properties["names"] = channel_names
        g.vertex_properties["size"] = num_users
        g.vertex_properties["id"] = channel_ids
        g.edge_properties["shu"] = raw_shared_users
        g.edge_properties["weights"] = scaled_shared_users
        g.save("linked_and_weighted.gt")


# A function to accomodate color scaling for recent activity overlay.
def clamp(x):
        if x > 1:
                return (1, 0, min((x * 0.25), 1))
        elif x < 0:
                return (0, min((x * -100.0), 1), 0)
        else:
                return (x, 0, 0)

# A function which defines and adds property-specific colorings to the graph.
# Current filter options: 
#     size -- colors by channel size (number of users)
#     team -- colors by channel name prefixes
#     recent -- colors by level of recent activity
# The property in "type" colors vertices, the property in "htype" colors halos.
def add_color_overlay(type, htype):
        if type == "":
                return
        print("halo")
        if not htype == "":
                add_color_overlay(htype, "")
                g = load_graph("colored.gt")
                halo = g.new_vertex_property("string")
                halo = g.vp.co
                g.vertex_properties["halo"] = halo
                                g.save("linked_and_weighted.gt")
        g = load_graph("linked_and_weighted.gt")
        color_overlay = g.new_vertex_property("string")
        
        if type == "size":
                for v in g.vertices():
                        if g.vp.size[v] < 5:
                                color_overlay[v] = "red"
                        elif g.vp.size[v] < 15:
                                color_overlay[v] = "orange"
                        elif g.vp.size[v] < 40:
                                color_overlay[v] = "yellow"
                        else:
                                color_overlay[v] = "green"
                                
        elif type == "team":
                for v in g.vertices():
                        name = g.vp.names[v]
                        if not name.find("ACHANNELPREFIX"):
                                color_overlay[v] = "rosybrown"
                        elif not name.find("ANOTHERCHANNELPREFIX"):
                                color_overlay[v] = "seagreen"
                        else:
                                color_overlay[v] = "aliceblue"
                                
        elif type == "recent":
                for v in g.vertices():
                        response = slack.api_call("channels.history", channel=g.vp.id[v], count=5)
                        message = response['messages']
                        time_dist = 0.00
                        for m in message:
                                mtime = float(m['ts'])
                                time_dist = time_dist + mtime
                        time_dist /= 5
                        scaled_val = (ts - time_dist) / 10000000
                        bounded = clamp(scaled_val)
                        red = (1 - bounded[0])
                        blue = bounded[0] + bounded[1] - bounded[2]
                        rgba = (red, bounded[1], blue, 0)
                        color_overlay[v] = to_hex(rgba)
                        
        g.vertex_properties["co"] = color_overlay
        g.save("colored.gt")


# Runs an attractive-repulsive force algorithm on the graph to determine layout.
def arfgraph():
        g = load_graph("colored.gt")
        # These are custom weights. You may want to experiment.
        arfpos = arf_layout(g, g.ep.weights, a=4, d=16, epsilon=1e-06, max_iter=10000)
        graph_draw(g, pos=arfpos, vertex_text=g.vp.names, vertex_font_size=14, vertex_fill_color=g.vp.co, 
              vertex_color=g.vp.halo, edge_pen_width=prop_to_size(g.ep.shu), output_size=(4000, 4000), 
              output="channels-linked-weighted.png")
        
# Sends the generated graph drawing to a channel of your choice.
def sendgraph():
        with open('channels-linked-weighted.png') as content:
                slack.api_call("files.upload", channels=dev_channel, file=content, title=graph_changes_message)

init_channelweb()
add_color_overlay("team", "recent")
arfgraph()
sendgraph()
                        
