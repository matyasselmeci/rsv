import time
from optparse import OptionParser

from esmond.api.client.perfsonar.query import ApiConnect, ApiFilters
from esmond.api.client.perfsonar.post import MetadataPost, EventTypePost, EventTypeBulkPost

# Set filter object
filters = ApiFilters()
gfilters = ApiFilters()

# Set command line options
parser = OptionParser()
parser.add_option('-d', '--disp', help='display metadata from specified url', dest='disp', default=False, action='store_true')
parser.add_option('-e', '--end', help='set end time for gathering data (default is now)', dest='end', default=0)
parser.add_option('-l', '--loop', help='include this option for looping process', dest='loop', default=False, action='store_true')
parser.add_option('-p', '--post',  help='begin get/post from specified url', dest='post', default=False, action='store_true')
parser.add_option('-r', '--error', help='run get/post without error handling (for debugging)', dest='err', default=False, action='store_true')
parser.add_option('-s', '--start', help='set start time for gathering data (default is -12 hours)', dest='start', default=-43200)
parser.add_option('-u', '--url', help='set url to gather data from (default is http://hcc-pki-ps02.unl.edu)', dest='url', default='http://hcc-pki-ps02.unl.edu')
parser.add_option('-w', '--user', help='the username to upload the information to the GOC', dest='username', default='afitz', action='store')
parser.add_option('-k', '--key', help='the key to upload the information to the goc', dest='key', default='fc077a6a133b22618172bbb50a1d3104a23b2050', action='store')
parser.add_option('-g', '--goc', help='the goc address to upload the information to', dest='goc', default='http://osgnetds.grid.iu.edu', action='store')
(opts, args) = parser.parse_args()

class EsmondUploader(object):
    
    def __init__(self,verbose,start,end,connect,username='afitz',key='fc077a6a133b22618172bbb50a1d3104a23b2050', goc='http://osgnetds.grid.iu.edu'):

        # Filter variables
        filters.verbose = verbose
        filters.time_start = time.time() + start
        filters.time_end = time.time() + end
        gfilters.verbose = False        
        gfilters.time_start = time.time() - 86400
        gfilters.time_end = time.time()

        # Username/Key/Location/Delay
        self.connect = connect
        self.username = username
        self.key = key
        print goc
        self.goc = goc
        self.conn = ApiConnect(self.connect,filters)
        self.gconn = ApiConnect(self.goc,gfilters)
                
        # Metadata variables
        self.destination = []
        self.input_destination = []
        self.input_source = []
        self.measurement_agent = []
        self.source = []
        self.subject_type = []
        self.time_duration = []
        self.tool_name = []
        self.event_types = []
        self.summaries = []
        self.datapoint = []
        self.metadata_key = []
        self.old_list = []
   
    # Get Existing GOC Data
    def getGoc(self):
        for gmd in self.gconn.get_metadata():
            self.old_list.append(gmd.metadata_key)
   
    # Get Data
    def getData(self,disp=False):
        self.getGoc()
        i = 0
        for md in self.conn.get_metadata():
            # Check for repeat data
            if md.metadata_key in self.old_list:
                continue
            else:
                # Assigning each metadata object property to class variables
                self.destination.append(md.destination)
                self.input_destination.append(md.input_destination)
                self.input_source.append(md.input_source)
                self.measurement_agent.append(md.measurement_agent)
                self.source.append(md.source)
                self.subject_type.append(md.subject_type)
                self.time_duration.append(md.time_duration)
                self.tool_name.append(md.tool_name)
                self.event_types.append(md.event_types)
                self.metadata_key.append(md.metadata_key)
                if disp:
                    print "\n\nNEW METADATA/DATA #" + str(i+1) + "\n"
                    print "Destination: " + self.destination[i]
                    print "Input Destination: " + self.input_destination[i]
                    print "Input Source: " + self.input_source[i]
                    print "Measurement Agent: " + self.measurement_agent[i]
                    print "Source: " + self.source[i]
                    print "Subject_type: " + self.subject_type[i]
                    print "Time Duration: " + self.time_duration[i]
                    print "Tool Name: " + self.tool_name[i]
                    print "Event Types: " + str(self.event_types[i])
                    print "Metadata Key: " + self.metadata_key[i]
                # Get Events and Data Payload
                temp_list = [] 
                temp_list2 = []
                temp_list3 = []
                for et in md.get_all_event_types():
                    temp_list.append(et.summaries)
                    dpay = et.get_data()
                    for dp in dpay.data:
                        tup = (dp.ts_epoch,dp.val)
                        temp_list2.append(tup)
                    temp_list3.append(temp_list2)
                self.datapoint.append(temp_list3)
                self.summaries.append(temp_list)
                # Print out summaries and datapoints if -d or --disp option is used
                if disp:
                    print "Summaries: " + str(self.summaries[i])
                    print "Datapoints: " + str(self.datapoint[i])
            i += 1
    # Post Data
    def postData(self):
        for i in range(len(self.destination)):
            # Looping through metadata
            args = {
                "subject_type": self.subject_type[i],
                "source": self.source[i],
                "destination": self.destination[i],
                "tool_name": self.tool_name[i],
                "measurement_agent": self.measurement_agent[i],
                "input_source": self.connect,
                "input_destination": self.goc,
                "time_duration": self.time_duration[i],
            }
        
            mp = MetadataPost(self.goc,username=self.username, api_key=self.key, **args)
            # Posting Event Types and Summaries
            for event_type, summary in zip(self.event_types[i], self.summaries[i]):
                mp.add_event_type(event_type)
                if summary:
                    mp.add_summary_type(event_type, summary[0][0], summary[0][1])
            new_meta = mp.post_metadata()
            # Posting Data Points
            for event_num in range(len(self.event_types[i])):
                for datapoint in self.datapoint[i][event_num]:
                ### Histograms were being rejected (wants dict, not list of dicts) disregarding them for now ###
                    if isinstance(datapoint[1], list):
                        if isinstance(datapoint[1][0], dict):
                            continue
                    if isinstance(datapoint[1], dict):
                        continue
                    et = EventTypePost(self.goc, username=self.username, api_key=self.key, metadata_key=new_meta.metadata_key, event_type=self.event_types[i][event_num])
                    et.add_data_point(datapoint[0],datapoint[1])
                    et.post_data()
