# table.py
# Marco Mambelli <marco@hep.uchicago.edu>

"""Table formatting to print list of elements.
"""


class Table(object):
    """Table formatting for lists of elements.
    Support fixed width columns:
    - truncate_quick: truncating the items at the specified width
    - truncate_leftright: in each column the first element is truncated on the left, 
      the following on the right. If an element is truncated, ellipses (...) are added.
      This is used for rsv-control listing
    - truncate: truncating the items to fit in the specified width. If an element is 
      truncated, ellipses (...) are added.
    Truncating options are evaluated in order and first ones supersede the followings
    """
    def __init__(self, columns=(), header_par=()):
        self.columns = columns
        self.header = ""
        self.truncate = True
        self.truncate_quick = False
        self.truncate_leftright = False
        self._buffer = []
        if header_par:
            self.makeHeader(*header_par)
        
    def setColumns(self, *cols):
        """Assigning the numbers to the column tuple""" 
        self.columns = cols
        
    def makeHeader(self, *header_par):
        """Create a formatted header string (usig the current style).
        Column widths should be set. Number of columns and element in the header should match.
        """
        header_args = header_par
        if not self.columns or len(self.columns) != len(header_args):
            #log.error("Invalid header")
            #return
            raise TableError("Invalid header. Columns not set or not matching.")
        self.header = self.format(*header_args)
        self.header += "\n"+'+'.join(['-'*i for i in self.columns])
        return
            
    # Setter and getter for header, probably to remove
    def setHeader(self, header):
        self.header = header
        
    def getHeader(self):
        return self.header
    
    def makeFormat(self):
        """Build a format string for table rows"""
        if not  self.columns:
            #log.error("Table columns not set")
            #return
            raise TableError("Table columns not set.")
        out = "%%-%ss" % (self.columns[0]-1)
        for i in self.columns[1:-1]:
            out += " | %%-%ss" % (i-2)
        if len(self.columns)>1:
            out += " | %%-%ss" % (self.columns[-1]-1)
        self.format_str = out
                
    # Setter and getter for format_str, should user access/modify it?
    def setFormat(self, format):
        self.format_str = format
        return
    
    def addToBuffer(self, *strval_par):
        """Add line to internal buffer"""
        self._buffer.append(strval_par)
        return

    def isBufferEmpty(self):
        if len(self._buffer) == 0:
            return True
        else:
            return False
    
    def formatBuffer(self, order_index=0, sort_=True):
        """Format and consume internal buffer.
        Returns a listed of formatted lines sorted in alphabetical order
        using the order_index column.
        If sort_ is false, sorting is disabled.
        All lines must be different to sort the buffer. No duplicate lines will be
        added by rsv-control.
        """
        # Still need to fix clashes when duplicate lines are in the buffer
        retlines = []
        if not sort_:
            for i in self._buffer:
                #multiline format to be faster?
                retlines.append(self.format(*(i)))
                self._buffer = []
                return retlines
        order_dic = {}        
        for i in self._buffer:
            key = "%s\t %s" % (i[order_index], i)
            order_dic[key] = i
        if len(self._buffer) != len(order_dic):
            #log.error("Key clash in table formatting")
            #return []
            raise TableError("Key clash in table formatting. Row not unique.")
        if order_dic:
            kl = order_dic.keys()
            kl.sort()
            for i in kl:
                #multiline format to be faster?
                retlines.append(self.format(*(order_dic[i])))
        self._buffer = []
        return retlines

    def format(self, *strval_par):
        """Format table rows.
        Number of arguments should match number of columns.
        """
        if not  self.columns or len(self.columns) != len(strval_par):
            #log.error("Table columns not set")
            #return None
            raise TableError("Table columns not set")
        if not self.format_str:
            self.makeFormat()
        strval = strval_par
        if self.truncate_quick:
            strval = [strval_par[0][:self.columns[0]-1],] 
            for i in range(len(self.columns)-2):
                strval.append(strval_par[i+1][:self.columns[i+1]-2])
            if len(self.columns)>1:
                strval.append(strval_par[-1][:self.columns[-1]-1])
        elif self.truncate_leftright:
            if len(strval_par[0])>=self.columns[0]:
                strval = ["..."+strval_par[0][4-self.columns[0]:],] 
            else:
                strval = [strval_par[0],]
            for i in range(len(self.columns)-2):
                if len(strval_par[i+1])+1>=self.columns[i+1]:
                    strval.append(strval_par[i+1][:self.columns[i+1]-5]+"...")
                else:
                    strval.append(strval_par[i+1])
            if len(self.columns)>1:
                if len(strval_par[-1])>=self.columns[-1]:
                    strval.append(strval_par[-1][:self.columns[-1]-4]+"...")
                else:
                    strval.append(strval_par[-1])
        elif self.truncate:
            increment = 0
            for i in range(len(self.columns)-1):
                if len(strval[i])+increment>=self.columns[i]:
                    strval[i] = strval[i][:(self.columns[i]-increment-4)]+"..."
                increment = 1
            if len(strval[-1])>=self.columns[-1]:
                strval[-1] = strval[-1][:(self.columns[-1]-4)]+"..."
        retval = self.format_str % tuple(strval)
        return retval

class TableError(Exception):
    """Error in Table formatting: inconsistent options, line clash
    """
    def __init__(self, message):
        self.message = message
         
    def __str__(self):
        return repr(self.message)
