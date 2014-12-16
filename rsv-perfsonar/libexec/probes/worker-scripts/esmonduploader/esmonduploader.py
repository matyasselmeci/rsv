import time
from time import strftime
from time import localtime

from optparse import OptionParser
from fractions import Fraction

from esmond.api.client.perfsonar.query import ApiConnect, ApiFilters
from esmond.api.client.perfsonar.post import MetadataPost, EventTypePost, EventTypeBulkPost

#allowedEvents = ['packet-loss-rate', 'packet-trace', 'packet-retransmits', 'throughput', 'throughput-subintervals', 'failures', 'packet-count-sent', 'packet-count-lost']

allowedEvents = ['packet-loss-rate', 'throughput', 'packet-trace', 'packet-retransmits', 'histogram-owdelay']

skipEvents = ['histogram-owdelay', 'histogram-ttl']

# Set filter object
filters = ApiFilters()
gfilters = ApiFilters()

# Set command line options
parser = OptionParser()
parser.add_option('-d', '--disp', help='display metadata from specified url', dest='disp', default=False, action='store')
parser.add_option('-e', '--end', help='set end time for gathering data (default is now)', dest='end', default=0)
parser.add_option('-l', '--loop', help='include this option for looping process', dest='loop', default=False, action='store_true')
parser.add_option('-p', '--post',  help='begin get/post from specified url', dest='post', default=False, action='store_true')
parser.add_option('-r', '--error', help='run get/post without error handling (for debugging)', dest='err', default=False, action='store_true')
parser.add_option('-s', '--start', help='set start time for gathering data (default is -12 hours)', dest='start', default=-43200)
parser.add_option('-u', '--url', help='set url to gather data from (default is http://hcc-pki-ps02.unl.edu)', dest='url', default='http://hcc-pki-ps02.unl.edu')
parser.add_option('-w', '--user', help='the username to upload the information to the GOC', dest='username', default='afitz', action='store')
parser.add_option('-k', '--key', help='the key to upload the information to the goc', dest='key', default='fc077a6a133b22618172bbb50a1d3104a23b2050', action='store')
parser.add_option('-g', '--goc', help='the goc address to upload the information to', dest='goc', default='http://osgnetds.grid.iu.edu', action='store')
parser.add_option('-t', '--timeout', help='the maxtimeout that the probe is allowed to run in secs', dest='timeout', default=1000, action='store')
parser.add_option('-x', '--summaries', help='upload and read data summaries', dest='summary', default=True, action='store')

(opts, args) = parser.parse_args()

class EsmondUploader(object):

    def add2log(self, log):
        print strftime("%a, %d %b %Y %H:%M:%S ", localtime()), log
    
    def __init__(self,verbose,start,end,connect,username='afitz',key='fc077a6a133b22618172bbb50a1d3104a23b2050', goc='http://osgnetds.grid.iu.edu'):

        # Filter variables
        filters.verbose = verbose
        filters.time_start = time.time() + start
        filters.time_end = time.time() + end
        gfilters.verbose = False        
        gfilters.time_start = time.time() + 5*start
        gfilters.time_end = time.time()
        gfilters.source = connect

        # Username/Key/Location/Delay
        self.connect = connect
        self.username = username
        self.key = key
        self.goc = goc
        self.conn = ApiConnect(self.connect, filters)
        self.gconn = ApiConnect(self.goc, gfilters)
                
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
    def getGoc(self, disp=False):
        if disp:
            self.add2log("Getting old data...")
        for gmd in self.gconn.get_metadata():
            self.old_list.append(gmd.metadata_key)
   
    # Get Data
    def getData(self, disp=False, summary=True):
        self.getGoc(disp)
        self.add2log("Only reading data for event types: %s" % (str(allowedEvents)))
        #self.add2log("Skipped reading data for event types: %s" % (str(skipEvents)))
        if summary:
            self.add2log("Reading Summaries")
        else:
            self.add2log("Omiting Sumaries")
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
                # print extra debugging only if requested
                self.add2log("Reading New METADATA/DATA %d" % (i+1))
                if disp:
                    print "Destination: " + self.destination[i]
                    print "Event Types: " + str(self.event_types[i])
                    print "Input Destination: " + self.input_destination[i]
                    print "Input Source: " + self.input_source[i]
                    print "Measurement Agent: " + self.measurement_agent[i]
                    print "Source: " + self.source[i]
                    print "Subject_type: " + self.subject_type[i]
                    if not self.time_duration[i] is None:
                        print "Time Duration: " + self.time_duration[i]
                    print "Tool Name: " + self.tool_name[i]
                    print "Metadata Key: " + self.metadata_key[i] + " /n/n"
                # Get Events and Data Payload
                # temp_list holds the sumaries for all event types for metadata i
                temp_list = [] 
                # temp_list3 is a list of lists. 
                # Each of its members are lists of datapoints of a given event_type
                temp_list3 = []
                # et = event type
                for eventype in self.event_types[i]: 
                    # temp_list2 is for adding all data points of a same event type
                    temp_list2 = []
                    et = md.get_event_type(eventype)
                    if summary:
                        temp_list.append(et.summaries)
                    else:
                        temp_list.append([])
                    # Skip readind data points for certain event types to improv efficiency  
                    if eventype not in allowedEvents:                                                                                                       
                    #if eventype in skipEvents:
                        #self.add2log("Skipped reading data for event type: %s for metadatda %d" % (eventype, i+1))
                        temp_list3.append(temp_list2)
                        continue
                    dpay = et.get_data()
                    for dp in dpay.data:
                        tup = (dp.ts_epoch, dp.val)
                        temp_list2.append(tup)
                    temp_list3.append(temp_list2)
                self.datapoint.append(temp_list3)
                self.summaries.append(temp_list)
            i += 1

    # Post Data
    def postData(self, disp=False):
        for i in range(len(self.destination)):
            # Looping through metadata
            args = {
                "subject_type": self.subject_type[i],
                "source": self.source[i],
                "destination": self.destination[i],
                "tool_name": self.tool_name[i],
                "measurement_agent": self.measurement_agent[i],
                "input_source": self.connect,
                "input_destination": self.goc
            }
            # Time duration may not always be set
            if not self.time_duration[i] is None:
                    args["time_duration"] = self.time_duration[i]        
            mp = MetadataPost(self.goc, username=self.username, api_key=self.key, **args)
            # Posting Event Types and Summaries
            for event_type, summary in zip(self.event_types[i], self.summaries[i]):
                mp.add_event_type(event_type)
                if summary:
                    mp.add_summary_type(event_type, summary[0][0], summary[0][1])
            self.add2log("posting NEW METADATA/DATA %d" % (i+1))
            if disp:
                print self.metadata_key[i]
            new_meta = mp.post_metadata()
            # Catching bad posts
            try:
                new_meta.metadata_key
            except:
                print 'WARNING'
                print args
                print self.event_types[i]
                print self.summaries[i]
                continue
            self.add2log("Finished posting summaries and metadata %d" % (i+1))
            # Posting Data Points
            et = EventTypeBulkPost(self.goc, username=self.username, api_key=self.key, metadata_key=new_meta.metadata_key)
            for event_num in range(len(self.event_types[i])):
                # datapoints are tuples the first field is epoc the second the value
                for datapoint in self.datapoint[i][event_num]:
                    # packet-loss-rate is read as a float but should be uploaded as a dict with denominator and numerator 
                    if 'packet-loss-rate' in self.event_types[i][event_num]:
                        if isinstance(datapoint[1], float):
                            packetLossFraction = Fraction(datapoint[1]).limit_denominator(300)
                            et.add_data_point(self.event_types[i][event_num], datapoint[0], {'denominator':  packetLossFraction.denominator, \
                                                                             'numerator': packetLossFraction.numerator})
                        else:
                            self.add2log("weird packet loss rate")
                    # For the rests the data points are uploaded as they are read
                    else:
                        et.add_data_point(self.event_types[i][event_num], datapoint[0], datapoint[1])
            # Posting the data once all data points on the same metadata have been added
            et.post_data()
            self.add2log("Finish posting data for metadata %d" % (i+1))
