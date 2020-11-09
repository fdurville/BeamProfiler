#! Python 3

#defining all necessary variables
import serial
import time

#version
v = 3.4

#scan number - added FD  20oct20
sn = 0
dataSaved = False

#setting default values for grbl / CNC control
grblPort = 'COM3'  # COM10 for Xtreme 8jan20
#COM7 for XYZ-lab - COM3 MyFlex11   -   COM for LabFlex
grblbdr = 115200
travelSpeed = 400

s = serial.Serial()     #com with Arduino/grbl

#default scanning parameters
gcodeStep = ''
stepXY = 0.1    #length value of a single step along both X and Y axis
stepZ = 5       #length value of a single step along Z axis
Xtravel = 10    #total distance of travel along X-axis
Ytravel = 4     #total distance of travel along Y-axis

travelX = 0     #length travelled along X-axis
travelY = 0     #length travelled along Y-axis
travelZ = 0     #length travelled along Z-axis

nstepX = 0      #Number of steps to take along X-axis
nstepY = 0      #Number of steps to take along Y-axis
nsteptot = 0    #total nb of steps tp be taken during chosen scan

nstepX = int( Xtravel * 0.5 / stepXY ) * 2
nstepY = int( Ytravel * 0.5 / stepXY ) * 2

gcodeTravelY = 'G01 Y'  + str(stepXY) + '\r \n'
gcodeTravelY = 'G01 Y'  + str(stepXY) + '\r \n'

travelCenterX = 0.5 * nstepX * stepXY + 1
travelCenterY = 0.5 * nstepY * stepXY + 1



#defining the type of scan desired - "X", "Y", "XY", "2D", "XYZ"
scanning = False
BPZ = False
scan = "XY"
stp = 0     #counter for nb step during scan
xstp = 0    #counter of nb of X-step taken during XY and 2D scan

#setting default values for DataSpider / data acquisition control
propPort = 'COM4'   # COM9 for Xtreme - COM4 for lab & MyFlex11
# COM8 for lab-Flex
propbdr = 115200
tout = 0.5

prop = serial.Serial()  #com with Propeller

#default sampling parameters
analogIn = '0'
duration = 0.1
samplingRate = 200          #sampling rate in samples per second
CLOCKPERSEC = 80000000
rateVal = CLOCKPERSEC / samplingRate

#parameters specific to communication protocol with DataSpider / Propeller
msgID = 1
EOP = "|"
ESC = "`"
# keyTable = {0:"talk",1:"over",2:"bad",3:"version",4:"start",5:"stop",
#6:"set",7:"dir",8:"query",9:"info",10:"dig",11:"wav",12:"point",
#13:"sync",14:"avg",15:"timer",16:"event",17:"resetevent",18:"trigger")} 
keyTable = ["talk","over","bad","version","start","stop","set","dir",\
            "query","info","dig","wav","point","sync",\
            "avg", "timer", "event", "resetevents", "trigger"]

#string messages used to communicate via pubsub to mainFrame
#no longer used
#graph = "graph"
#stopScan = "stopScan"


#default variables used for data acquisition and processing
Analysis = False
nptMax = 1000
data = []
imgData = []
BPZ = []
centroid = [0,0]
secMoment = [0,0]
sumI = [0,0]
bkg = 0

#storing essential scan values in a single list
#dataInput = [grblPort, step, travel, analogIn ,duration, propPort, stepZ, travelZ, scan, Ytravel]
dataInput = [grblPort, stepXY, stepZ, nstepX, nstepY, xstp, travelZ, propPort, analogIn ,duration ]

#variables used for graphing
colorTable = [ "blue", "red", "green", "yellow", "purple", "black" ]
xlabel = "mm"
ylabel = "Value"
maxVal = 4095
minVal = 0


### --- Update values of all parameters and variables
def updateSteps():
    global nsteptot, nstepX, nstepY, gcodeTravelX, gcodeTravelY,\
           travelCenterX, travelCenterY
    nstepX = int( Xtravel * 0.5 / stepXY ) * 2
    nstepY = int( Ytravel * 0.5 / stepXY ) * 2
    gcodeTravelX = 'G01 X'  + str(stepXY) + '\r \n'
    gcodeTravelY = 'G01 Y'  + str(stepXY) + '\r \n'
    travelCenterX = 0.5 * nstepX * stepXY + 1
    travelCenterY = 0.5 * nstepY * stepXY + 1
    
    if scan == "X":
        nsteptot = nstepX
        print ("Xscan nsteptot: "), nsteptot
    elif scan == "Y":
        nsteptot = nstepY
    elif scan == "XY":
        nsteptot = nstepX + nstepY + 1
    elif scan == "2D":
        nsteptot = ( nstepX + 1 ) * ( nstepY + 1 ) - 1
    else:
        print ("error: no scan selected")
        nsteptot = 0

### --- reset data for new scan
def resetData():
    data = []
    imgData = []
    BPZ = []
    centroid = [0,0]
    secMoment = [0,0]
    sumI = [0,0]
    bkg = 0

### --- reset data for dataprocessing
def resetProcess():
    centroid = [0,0]
    secMoment = [0,0]
    sumI = [0,0]
    bkg = 0



### --- Loop to just read and parse data from propeller
def readData(duration):
    #chIdx = int(dataInput[3])
    datValr = 0
    nn = 0
    nc = 0
    dd = 0
    de = 0
    
    while dd == 0:
        valr = []   # store values of individual data point
        nb = 0
        t = time.time() + duration

        try:
            if prop is None:
                prop = serial.Serial(propPort,propbdr)
                prop.timeout = 0.5
            else:
                if not prop.isOpen():
                    prop = serial.Serial(propPort,propbdr)
                    prop.timeout = 0.5
        except NameError:
            prop = serial.Serial(propPort,propbdr)
            prop.timeout = 0.5
    
        prop.flush()
        while t - time.time() > 0:
            time.sleep(0.0002)
        try:
            nb = prop.in_waiting
            print ("----------------- rcvd nb:------------"), nb
        except:
            print ("error - no bytes received")
            dd = 0

        if nb > 12:
            #print "received > 12 byte - this should be a valid data message"
            #msgr = prop.read(prop.in_waiting)
            msgr = prop.read(nb)
            #print "received:  ",msgr
            nc = 0
            chk = 0
            for c in msgr:
                #print "c in msgr: ", c
                if ord(c) == 124:
                    nn += 1
                    if nc < (len(msgr) - 1) and nc > 9 and ord(msgr[nc - 10]) == 12: #-out FD 12jul18 11:57am
                        #verifying chksum
                        chk = ord(msgr[nc+1])    #chksum value of message sent
                        chksum = 0
                        for ii in range(0,10):  #computing chksum of message received
                            chksum = ((chksum<<1) | (chksum>>7)) & 255  # left-rotate
                            chksum = (chksum + ord(msgr[nc - (10 - ii)])) & 255  # 8-bit addition
                        if chksum == chk:       #chksums match valid data
                            pVal = ord(msgr[nc - 5]) + (ord(msgr[nc - 6]) & 15) * 256
                            valr.append(pVal)    #store all good values in list valr
                        else:
                            #not sure what to do if chksums do not match. At this point, just skip data packet
                            print ("chksum failed!!!!")
                            pass
                    else:
                        print "the EOP does not match a data packet"
                        pass    #the EOP does not match a data packet FD 12jul18
                nc += 1
                
            
        if valr is not None and len(valr) != 0:
            datValr = sum(valr) / len(valr)
            if datValr != 0:
                dd = 1
            else:
                dd = 0
                print ("received data is 0 - Retry 10X to read data")
                de += 1
                if de > 10:
                    print ("tried 10 times - giving up - taking 0 as valid data")
                    de = 0
                    dd = 1
        else:
            print ("error - no values read. Retry."),valr
            dd = 0
            de +=1
            if de > 10:
                print ("tried 10 times - giving up - taking 0 as data")
                de = 0
                dd = 1
        del valr        #added 30jan20 - FD
    return datValr
        
#+++++++++++++Functions specific to propeller-DataSpider++++++++++++++++
# functino nextMsgID() return Int as a sequential message ID.
def nextMsgID(msgID):
    msgID = int(msgID + 1) & 255
    if msgID == 0:
        msgID = int(msgID + 1) & 255
    return msgID

# function to send actual message to propeller-DataSpider
def send(msgID, prop, key, value=None ):
    #""" sends a control packet with a message ID that corresponds to the string value 'key', with parameters specified in value.
    #key is a string that represents the message ID, or and int specifing the message ID.
    #value is either an integer, or a list of integers."""
    #i.e., to set data rate, value is a list of 2 numbers: the channel nb, and the rate
    #print "getting msgID"
    #print "value: ", value

    if prop is None :
        print("send on bad port")
        return -1
    
    if key is None:
        print("send NoneType key", key)
        return -1

    try:
        msg = chr(key) + chr(nextMsgID(msgID))
        #print "key is integer.... char: ", chr(key)
    except TypeError: # key is not an int. treat as string.         
        if key not in keyTable and key :
            print("Attempting invalid control msg ID", key)
            return -1
        msg = chr(keyTable.index(key)) + chr(nextMsgID(msgID))
        #print "key index: ", keyTable.index(key), "char: ",chr(keyTable.index(key)) 

    if value is not None:
        #print "value: ", value
        try:
            for v in value:
                #print "value is a list"
                for n in range(4):
                    msg += chr( (v>>24-n*8)&255 )
                    #print "v:", v, "n: ", n, "add-msg: ", (v>>24-n*8)&255
        except TypeError: # value is not a list. treat as int.
            #print "value treated as integer"
            for n in range(4):
                #print "n: ", n, "add-msg: ", (int(value)>>24-n*8)&255
                msg += chr( (int(value)>>24-n*8)&255 )
    msg = msg.replace(ESC, ESC+ESC)
    msg = msg.replace(EOP, ESC+EOP)
    chksum = 0
    for c in msg:
        chksum = ((chksum<<1) | (chksum>>7)) & 255 # left-rotate
        chksum = (chksum + ord(c)) % 256           # 8-bit addition

    msg = msg + EOP + chr(chksum) #completing the message with EOP + chksum

    try:
        retv = prop.write(msg)
    except (serial.serialutil.portNotOpenError, ValueError, serial.serialutil.SerialTimeoutException) as err:
        print("Writing to closed port", err)
        return -1
    except serial.SerialException as err:
        print("SerialException on write", err)
        return -1
    #self.comlock.release()
    return 1 

#function to start reading a Analog-to-Digital Converrter channel on propeller-DataSpider
def startADC(port,bdr,chan,rate):
    print ("-----"), port,"--", bdr,"--",chan,"--",rate
    msgID = 1
    val = [chan,rate]
    
    try:
        if prop is None:
            prop = serial.Serial(port,bdr)
            prop.timeout = 0.5
        else:
            if not prop.isOpen():
                prop = serial.Serial(port,bdr)
                prop.timeout = 0.5
    except NameError:
        prop = serial.Serial(port,bdr)
        prop.timeout = 0.5
    
    ttt = send(msgID, prop,'set',val)  #setting rate
    ttt = send(nextMsgID(msgID), prop,'start',2**chan)  #start ADC
    print "startADC ttt: ", ttt
    if ttt != 1:
        print ("-------startADC failure....")
    time.sleep(0.2)      #allow some time for the prop-chip to respond


#function to stop reading a Analog-to-Digital Converrter channel on propeller-DataSpider
def stopADC(chan):
    #global prop
    ttt = send(nextMsgID(msgID), prop,'stop',2**chan)  #start ADC
    try:
        if prop.isOpen():
            prop.close()
            print ("propComPort is now closed.")
        else:
            print ("prop is already clsoed")
    except:
        print ("error trying to close prop")

#+++++++++++++End Of propeller-DataSpider Functions++++++++++++++++++++





