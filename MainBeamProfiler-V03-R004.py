#! Python 3

import wx
import wx.lib.buttons as buttons
import serial
import time
import threading
import pickle
import wx.lib.plot
import os, sys
import numpy as np
import DataProcessing as dp
import BeamProfiler as bp
import imgConv as ic
import math
from PIL import Image


#Combine translation stage with data-acquisition
#translation stage is controlled by Arduino running Grbl
#data acquisition is controlled by Parallax-Propeller (DataSpider module)
#BeamProfiler V000 started from XYZ-scan-V013   -   6 Feb 2020-FD
#First mod: separate functions into files
#Module BeamProfiler contains all global variables used,
#along with functions specific to data acquisition from DataSpider / Propeller
#Module DataProcessing contains all functions specific to data processing
#such as subtracting bkg value, calculating centroid and second moment
#Module ScanningFunctions contains functions specific to "scanning"
#i.e., synchronizing moving stages and requesting data-acquisition

#V03-R001 - modified menu bar, added status bar - FD-04jul20
#added info on status bar
#added serial number for each scan
#added Z-zeroing button

#V03-R002  -  FD-25oct20  -  adding time acquisition - WIP
#V3.4  -  FD-05nov20  -  adding Beam Parameters BP save function
#save in file BP.csv,
#appending the calculated beam parameters from successjve XY scans
#added bp.BPZ boolean variable for this
#also added tracking moving X & Y

#version
v = 3.4


V = "V" + str(v)

if bp.v != v or dp.v != v :
    print ("modules are not correct version")

title = "X-Y-Z Scan - All values in mm and seconds - " + V
xSize = 800         #H-size of window frame
ySize = 700         #V-size of window frame
btnSize = 40        #size of START button
panelWidth = 180    #width of left panel

bkgStyle = (wx.DEFAULT_FRAME_STYLE | wx.STAY_ON_TOP) & ~(wx.RESIZE_BORDER | wx.MAXIMIZE_BOX)

class MyFrame(wx.Frame):
    def __init__(self, parent, title, xSize, ySize, panelWidth):
        wx.Frame.__init__(self, parent, panelWidth, title=title, size=(xSize, ySize))

        ico = wx.Icon('OFSI.ico', wx.BITMAP_TYPE_ICO )
        self.SetIcon( ico )

        global plot, mf, bkgReceived
        mf = self
        bkgReceived = False

        #timer used for data-acquisition
        self.stepTimer = wx.Timer(self)        

        #setting up variable with default values
        bp.updateSteps()
        self.grblPort = bp.grblPort
        self.stepXY = bp.stepXY
        self.Xtravel = bp.Xtravel
        self.Ytravel = bp.Ytravel
        self.nstepX = bp.nstepX
        self.nstepY = bp.nstepY
        self.nsteptot = bp.nsteptot
        self.analogIn = bp.analogIn
        self.duration = bp.duration
        self.propPort = bp.propPort
        self.stepZ = bp.stepZ
        self.travelZ = bp.travelZ
        self.scan = bp.scan

        self.scanList = ['X','Y','XY','2D','XYZ']

        self.centroid = bp.centroid

        #print "default values: ", self.grblPort, self.stepXY, self.Xtravel,\
                        #self.Ytravel, self.stepZ, self.travelZ,\
                        #self.analogIn, self.duration, self.propPort


        #defining all event handlers
        def getComPort(event):
            self.grblPort = self.gcomPort.GetValue()
            print ("selected port: "), self.grblPort
            bp.grblPort = self.grblPort
            return self.grblPort

        def getStepXY(event):
            self.stepXY = float(self.stepSize.GetValue())
            print ("step: "), self.stepXY
            bp.stepXY = self.stepXY
            bp.updateSteps()
            graph()
            self.updateStat('',1)
            return self.stepXY

        def getStepZ(event):
            self.stepZ = float(self.stepZSize.GetValue())
            print ("stepZ: "), self.stepZ
            bp.stepZ = self.stepZ
            self.updateStat('',1)
            return self.stepZ

        def getXTravel(event):
            global mf
            self.Xtravel = float(self.totalTravel.GetValue())
            print ("Xtravel: "), self.Xtravel
            bp.Xtravel = self.Xtravel
            bp.updateSteps()
            graph()
            self.updateStat('',1)
            return self.Xtravel
    
        #added 12mar20/FD
        def getYtravel(event):
            global mf
            self.Ytravel = float(self.totalYtravel.GetValue())
            print ("Ytravel: "), self.Ytravel
            bp.Ytravel = self.Ytravel
            bp.updateSteps()
            graph()
            self.updateStat('',1)
            return self.Ytravel
    
        def getPropPort(event):
            self.propPort = self.propComPort.GetValue()
            print ("selected prop port: "), self.propPort
            bp.propPort = self.propPort
            return self.propPort

        def getChanIn(event):
            self.analogIn = self.chanIn.GetValue()
            print ("selected AI-"),self.analogIn
            bp.analogIn = self.analogIn
            return self.analogIn

        def getDuration(event):
            self.duration = float(self.durAcq.GetValue())
            print ("duration: "), self.duration
            bp.duration = self.duration
            self.updateStat('',1)
            return self.duration

        def getBillboard(event):
            #time.sleep(1)
            billboard = BillboardDisplay(self)
            billboard.Show()

        def getGraph(event):
            #time.sleep(1)
            tgraph = TimeGraph(self)
            tgraph.Show()

        def moveLeft(event):
            global mf
            mf.statusbar.PushStatusText('moving left')
            grblPort = bp.grblPort
            stepXY = bp.stepXY
            try:
                if bp.s is None:
                    startArduino(grblPort,bp.grblbdr)
                else:
                    if not bp.s.isOpen():
                        bp.s.open()
            except:
                startArduino(grblPort,bp.grblbdr)
            gcode = 'G01 X-'  + str(stepXY)
            sendCode(gcode)
            bp.travelX = bp.travelX - stepXY
            print ('Xoffset: '),bp.travelX
            time.sleep(1)
            mf.statusbar.PushStatusText('  ')
            self.updateStat('',1)

        def moveRight(event):
            global mf
            self.updateStat('moving right',0)
            grblPort = bp.grblPort
            stepXY = bp.stepXY
            try:
                if bp.s is None:
                    startArduino(grblPort,bp.grblbdr)
                else:
                    if not bp.s.isOpen():
                        bp.s.open()
            except:
                startArduino(grblPort,bp.grblbdr)
            gcode = 'G01 X'  + str(stepXY)
            sendCode(gcode)
            bp.travelX = bp.travelX + stepXY
            print ('Xoffset: '),bp.travelX
            time.sleep(1)
            self.updateStat(' ',0)
            self.updateStat('',1)

        def moveDown(event):
            #global s
            self.updateStat('moving down',0)
            grblPort = bp.grblPort
            stepXY = bp.stepXY
            try:
                if bp.s is None:
                    startArduino(grblPort,bp.grblbdr)
                else:
                    if not bp.s.isOpen():
                        bp.s.open()
            except:
                startArduino(grblPort,bp.grblbdr)
            gcode = 'G01 Y-'  + str(stepXY)
            sendCode(gcode)
            time.sleep(0.5)
            bp.travelY = bp.travelY - stepXY
            print ('Yoffset: '),bp.travelY
            self.updateStat('     ',0)
            self.updateStat('',1)

        def moveUp(event):
            #global s
            self.updateStat('moving up',0)
            grblPort = bp.grblPort
            stepXY = bp.stepXY
            try:
                if bp.s is None:
                    startArduino(grblPort,bp.grblbdr)
                else:
                    if not bp.s.isOpen():
                        bp.s.open()
            except:
                startArduino(grblPort,bp.grblbdr)
            gcode = 'G01 Y'  + str(stepXY)
            sendCode(gcode)
            bp.travelY = bp.travelY + stepXY
            print ('Yoffset: '),bp.travelY
            time.sleep(0.5)
            self.updateStat('     ',0)
            self.updateStat('',1)

        def moveBack(event):
            #global s
            self.updateStat('moving back',0)
            grblPort = bp.grblPort
            stepZ = bp.stepZ
            travelZ = bp.travelZ
            try:
                if bp.s is None:
                    startArduino(grblPort,bp.grblbdr)
                else:
                    if not bp.s.isOpen():
                        bp.s.open()
            except:
                startArduino(grblPort,bp.grblbdr)
            gcode = 'G01 Z-'  + str(stepZ)
            sendCode(gcode)
            travelZ = travelZ - stepZ
            bp.travelZ = travelZ
            self.horZPos.SetLabel(label = "Z=" + str(bp.travelZ))
            time.sleep(0.5)
            self.updateStat('     ',0)

        def moveFwd(event):
            #global s
            self.updateStat('moving forward',0)
            grblPort = bp.grblPort
            stepZ = bp.stepZ
            travelZ = bp.travelZ
            try:
                if bp.s is None:
                    startArduino(grblPort,bp.grblbdr)
                else:
                    if not bp.s.isOpen():
                        bp.s.open()
            except:
                startArduino(grblPort,bp.grblbdr)
            gcode = 'G01 Z'  + str(stepZ)
            sendCode(gcode)
            travelZ = travelZ + stepZ
            bp.travelZ = travelZ
            self.horZPos.SetLabel(label = "Z=" + str(bp.travelZ))
            time.sleep(0.5)
            self.updateStat('    ',0)

        def zeroZ(event):
            #global s
            grblPort = bp.grblPort
            try:
                if bp.s is None:
                    startArduino(grblPort,bp.grblbdr)
                else:
                    if not bp.s.isOpen():
                        bp.s.open()
            except:
                startArduino(grblPort,bp.grblbdr)
            gcode = 'G92 Z0'
            sendCode(gcode)
            travelZ = 0
            bp.travelZ = travelZ
            self.horZPos.SetLabel(label = "Z=" + str(bp.travelZ))

        def getScan(event):
            self.scan = self.scanType.GetValue()
            print ("selected scan: "), self.scan
            bp.scan = self.scan
            bp.updateSteps()
            graph()
            self.updateStat('',1)
            if self.scan == 'XYZ':
                #should open window with explanation how it will work
                header = "BP Data from MainBeamProfiler"
                saveBP(self,header)
                bp.BPZ = True
                self.scan = 'XY'
                bp.scan = self.scan
            return self.scan

        def getStart(event):
            self.value = self.pulseBtn.GetValue()
            if self.stepTimer.IsRunning():
                print ("TIMER RUNNING!!!!!!")
                self.stepTimer.Stop()
                print ("TIMER IS STOPPED")
            if self.value:
                if len(bp.data) != 0:
                    del bp.data[0:len(bp.data)]
                self.btnLabel.SetLabel('STOP')
                #imgData = startScan(self)
                self.updateStat('start scan',0)
                bp.sn = bp.sn + 1
                startScan(self)
            else:
                self.stopScan()
                #self.btnLabel.SetLabel('START')

        #this is not used
        def getSave(event):
            print ("saving data...")
            self.updateStat('saving data',0)
            header = "Data from MainBeamProfiler"
            saveData(self,header)


        #this is not used
        def getSaveBP(event):
            print ("saving BP data...")
            self.updateStat('saving BP data',0)
            header = "BP Data from MainBeamProfiler"
            saveBP(self,header)

        def updateStatus(msg,f):
            global mf
            if msg == "":
                msg = 'scan' + str(bp.scan) + ' Nb: ' + str(bp.sn)\
                      + '  X' + str(bp.Xtravel) + '  Y' + str(bp.Ytravel) \
                      + '  stp' + str(bp.stepXY) + '  dur' + str(bp.duration)

                mf.statusbar.SetStatusText(msg, f)
                mf.statusbar.SetStatusText("WIP - 000", 0)
        

        ###---end of event handlers



            

        ###---setting up all visual elements of GUI / frame / display / window
            
        ###--- seting up menu-bar
        # create the menubar
        menuBar = wx.MenuBar()
        # create a first menu
        firstMenu = wx.Menu()
        saveMenuItem = firstMenu.Append(100, "SaveAll","save all data in file")
        saveBPMenuItem = firstMenu.Append(101, "Save BP","save Beam Parameters in file")
        # create a 2nd menu
        secondMenu = wx.Menu()
        bkgMenuItem = secondMenu.Append(200, "Background","subtract background")
        centerMenuItem = secondMenu.Append(201, "Center","Calculate centroid")
        widthMenuItem= secondMenu.Append(202, "Width","Calculate second-moment")
        allMenuItem= secondMenu.Append(203, "All","Calculate all parameters")
        # create a 3rd menu
        thirdMenu = wx.Menu()
        infoMenuItem = thirdMenu.Append(300, "About","info on this")
        # add menu to menubar
        menuBar.Append(firstMenu, "&File")
        menuBar.Append(secondMenu, "&Analysis")
        menuBar.Append(thirdMenu, "&About")
        # bind actions
        self.Bind(wx.EVT_MENU, saveData, saveMenuItem)
        self.Bind(wx.EVT_MENU, saveBP, saveBPMenuItem)
        self.Bind(wx.EVT_MENU, self.bkgCor, bkgMenuItem)
        self.Bind(wx.EVT_MENU, self.calcCentroid, centerMenuItem)
        self.Bind(wx.EVT_MENU, self.calcWidth, widthMenuItem)
        self.Bind(wx.EVT_MENU, self.dataAnalysis, allMenuItem)
        self.Bind(wx.EVT_MENU, self.info, infoMenuItem)
        # activate menubar
        self.SetMenuBar(menuBar)

        #creating a status bar with 2 fields to display messages
        self.statusbar = self.CreateStatusBar(2)
        self.statusbar.SetStatusWidths([panelWidth, -1])
        #self.statusbar.SetStatusText('...')
        #self.statusbar.SetStatusText('...', 1)

        #setting up font size and type for labels
        font = wx.Font(12,wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False)
        font2 = wx.Font(11,wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, True)
        
        #setting up a vertically-split window
        self.splitter = wx.SplitterWindow(self, -1, style=wx.SP_LIVE_UPDATE)
        self.grblPanel = wx.Panel(self.splitter, -1)
        self.graphPanel = wx.Panel(self.splitter, -1)
        #self.graphPanel.SetBackgroundColour(wx.WHITE)

        self.splitter.SplitVertically(self.grblPanel, self.graphPanel,panelWidth)

        # add plot on graphPanel
        self.plotSizer = wx.BoxSizer(wx.VERTICAL)
        plot = wx.lib.plot.PlotCanvas(self.graphPanel, size=wx.Size(500,500), style=wx.EXPAND)
        plot.SetShowScrollbars(False)

        #setting up sizers for graphPanel
        self.plotSizer.Add(plot,1,wx.EXPAND,0)
        graphPnlSizr = wx.BoxSizer(wx.VERTICAL)
        graphPnlSizr.Add(self.plotSizer, 1, wx.EXPAND, 0)
        self.graphPanel.SetSizer(graphPnlSizr)

        # grbl-COM-Port combobox Control
        self.portList = ['COM3','COM4','COM5','COM6','COM7','COM8', 'COM9', 'COM10', 'COM11', 'COM12','COM13']
        self.gportLabel = wx.StaticText(self.grblPanel, label="Grbl Port")
        self.gcomPort = wx.ComboBox(self.grblPanel, choices=self.portList, value=self.grblPort, style=wx.CB_READONLY)
        self.Bind(wx.EVT_COMBOBOX, getComPort, self.gcomPort)
        s1 = wx.BoxSizer(wx.HORIZONTAL)
        s1.Add(self.gportLabel, 0, wx.ALL,2)
        s1.Add(self.gcomPort, 0, wx.ALL,2)

        #XY-step size entry box
        self.stepLabel = wx.StaticText(self.grblPanel, wx.ID_ANY, 'XY Stp ')
        self.stepSize = wx.TextCtrl(self.grblPanel, wx.ID_ANY, str(bp.stepXY), style=wx.TE_PROCESS_ENTER)
        self.stepSize.Bind(wx.EVT_TEXT_ENTER, getStepXY)
        s2 = wx.BoxSizer(wx.HORIZONTAL)
        s2.Add(self.stepLabel, 0, wx.ALL,2)
        s2.Add(self.stepSize, 1, wx.ALL,2)

        #total travelX entry box
        self.travelLabel = wx.StaticText(self.grblPanel, wx.ID_ANY, 'Xtravel')
        self.totalTravel = wx.TextCtrl(self.grblPanel, wx.ID_ANY,str(bp.Xtravel),style=wx.TE_PROCESS_ENTER)
        self.totalTravel.Bind(wx.EVT_TEXT_ENTER, getXTravel)
        s3 = wx.BoxSizer(wx.HORIZONTAL)
        s3.Add(self.travelLabel, 0, wx.ALL,2)
        s3.Add(self.totalTravel, 1, wx.ALL,2)
        s3.SetDimension(-1,-1,90,-1)
        
        #total travelY entry box --- added FD/12mar20
        self.YtravelLabel = wx.StaticText(self.grblPanel, wx.ID_ANY, 'Ytravel')
        self.totalYtravel = wx.TextCtrl(self.grblPanel, wx.ID_ANY,str(bp.Ytravel),style=wx.TE_PROCESS_ENTER)
        self.totalYtravel.Bind(wx.EVT_TEXT_ENTER, getYtravel)
        s4 = wx.BoxSizer(wx.HORIZONTAL)
        s4.Add(self.YtravelLabel, 0, wx.ALL,2)
        s4.Add(self.totalYtravel, 1, wx.ALL,2)
        s4.SetDimension(-1,-1,90,-1)
        
        #Z-step size entry box
        self.stepZLabel = wx.StaticText(self.grblPanel, wx.ID_ANY, 'Z Stp ')
        self.stepZSize = wx.TextCtrl(self.grblPanel, wx.ID_ANY, str(bp.stepZ), style=wx.TE_PROCESS_ENTER)
        self.stepZSize.Bind(wx.EVT_TEXT_ENTER, getStepZ)
        s5 = wx.BoxSizer(wx.HORIZONTAL)
        s5.Add(self.stepZLabel, 0, wx.ALL,2)
        s5.Add(self.stepZSize, 1, wx.ALL,2)

        #setting up manual movement of stage
        self.moveStageBox = wx.StaticBox(self.grblPanel, -1, 'Move Stage')
        self.moveStageBox.SetFont(font)
        s20 = wx.StaticBoxSizer(self.moveStageBox, wx.VERTICAL)
        self.stageNote = wx.StaticText(self.grblPanel, label = '(increments of Step Size)')
        stageNoteSizer = wx.BoxSizer(wx.VERTICAL)
        stageNoteSizer.Add(self.stageNote, 0, wx.ALIGN_CENTER)
        stageNoteSizer.AddSpacer(2)
        s20.Add(stageNoteSizer, 0, wx.ALIGN_LEFT, 0)

        #Added labels X and Y, and buttons Down and Up - FD 31may18
        self.horizontalNote = wx.StaticText(self.grblPanel, label = "Horizontal X")
        horizontalNoteSizer = wx.BoxSizer(wx.VERTICAL)
        horizontalNoteSizer.Add(self.horizontalNote, 0, wx.ALIGN_CENTER)
        s20.Add(horizontalNoteSizer, 0, wx.ALIGN_CENTER, 0)
        
        self.moveLeftBtn = wx.Button(self.grblPanel, id=wx.ID_ANY, label = " - <<< ", size = (70,-1))
        self.moveRightBtn = wx.Button(self.grblPanel, id=wx.ID_ANY, label = " >>> + ", size = (70,-1))
        self.moveLeftBtn.Bind(wx.EVT_BUTTON, moveLeft)
        self.moveRightBtn.Bind(wx.EVT_BUTTON, moveRight)
        moveBtnSizer = wx.BoxSizer(wx.HORIZONTAL)
        moveBtnSizer.Add(self.moveLeftBtn,0,wx.CENTER)
        moveBtnSizer.Add(self.moveRightBtn, 0, wx.CENTER)
        s20.Add(moveBtnSizer, 0, wx.EXPAND, 0)

        self.verticalNote = wx.StaticText(self.grblPanel, label = "Vertical Y")
        verticalNoteSizer = wx.BoxSizer(wx.VERTICAL)
        verticalNoteSizer.Add(self.verticalNote, 0, wx.ALIGN_CENTER)
        s20.Add(verticalNoteSizer, 0, wx.ALIGN_CENTER, 0)
        
        self.moveDownBtn = wx.Button(self.grblPanel, id=wx.ID_ANY, label = "- \/ \/", size = (70,-1))
        self.moveUpBtn = wx.Button(self.grblPanel, id=wx.ID_ANY, label = " /\ /\ +", size = (70,-1))
        self.moveDownBtn.Bind(wx.EVT_BUTTON, moveDown)
        self.moveUpBtn.Bind(wx.EVT_BUTTON, moveUp)
        moveYBtnSizer = wx.BoxSizer(wx.HORIZONTAL)
        moveYBtnSizer.Add(self.moveDownBtn,0,wx.CENTER)
        moveYBtnSizer.Add(self.moveUpBtn, 0, wx.CENTER)
        s20.Add(moveYBtnSizer, 0, wx.EXPAND, 0)

        #adding Z-controls 
        self.horizontalZNote = wx.StaticText(self.grblPanel, label = "Z-axis")
        horizontalZNoteSizer = wx.BoxSizer(wx.VERTICAL)
        horizontalZNoteSizer.Add(self.horizontalZNote, 0, wx.ALIGN_CENTER)
        s20.Add(horizontalZNoteSizer, 0, wx.ALIGN_CENTER, 0)
        
        self.moveBwdBtn = wx.Button(self.grblPanel, id=wx.ID_ANY, label = "- <<< ", size = (70,-1))
        self.moveFwdBtn = wx.Button(self.grblPanel, id=wx.ID_ANY, label = " >>> +", size = (70,-1))
        self.moveBwdBtn.Bind(wx.EVT_BUTTON, moveBack)
        self.moveFwdBtn.Bind(wx.EVT_BUTTON, moveFwd)
        moveZBtnSizer = wx.BoxSizer(wx.HORIZONTAL)
        moveZBtnSizer.Add(self.moveBwdBtn,0,wx.CENTER)
        moveZBtnSizer.Add(self.moveFwdBtn, 0, wx.CENTER)
        s20.Add(moveZBtnSizer, 0, wx.EXPAND, 0)

        #adding Z-position - 23 jan 20  - added Z-zero - 21 oct 20 
        self.horZPos = wx.StaticText(self.grblPanel, label = "Z=" + str(bp.dataInput[6]), size = (50,-1))
        self.horZPos.SetFont(font2)
        self.zeroZBtn = wx.Button(self.grblPanel, id=wx.ID_ANY, label = "Z0", size = (35,-1))
        self.zeroZBtn.Bind(wx.EVT_BUTTON, zeroZ)
        horZposSzr = wx.BoxSizer(wx.HORIZONTAL)
        horZposSzr.Add(self.horZPos, 0, wx.ALIGN_LEFT)
        horZposSzr.Add(self.zeroZBtn, 0, wx.RIGHT)
        s20.Add(horZposSzr, 0, wx.ALIGN_CENTER, 0)


        # CH-IN combobox Control
        self.chanList = ['0', '1', '2', '3']
        self.chanLabel = wx.StaticText(self.grblPanel, label="Analog Input")
        self.chanIn = wx.ComboBox(self.grblPanel, choices=self.chanList, value=self.analogIn, style=wx.CB_READONLY)
        self.Bind(wx.EVT_COMBOBOX, getChanIn, self.chanIn)
        s30 = wx.BoxSizer(wx.HORIZONTAL)
        s30.Add(self.chanLabel, 0, wx.ALL,2)
        s30.Add(self.chanIn, 0, wx.ALL,2)

        #acquisition duration entry box
        self.durationLabel = wx.StaticText(self.grblPanel, wx.ID_ANY, 'Duration')
        self.durAcq = wx.TextCtrl(self.grblPanel, wx.ID_ANY,str(self.duration),style=wx.TE_PROCESS_ENTER)
        self.durAcq.Bind(wx.EVT_TEXT_ENTER, getDuration)
        s31 = wx.BoxSizer(wx.HORIZONTAL)
        s31.Add(self.durationLabel, 0, wx.ALL,2)
        s31.Add(self.durAcq, 0, wx.ALL,2)

        # Prop COM-Port combobox Control
        self.propPortLabel = wx.StaticText(self.grblPanel, label="Prop Port")
        self.propComPort = wx.ComboBox(self.grblPanel, choices=self.portList, value=self.propPort, style=wx.CB_READONLY)
        self.Bind(wx.EVT_COMBOBOX, getPropPort, self.propComPort)
        s32 = wx.BoxSizer(wx.HORIZONTAL)
        s32.Add(self.propPortLabel, 0, wx.ALL,2)
        s32.Add(self.propComPort, 0, wx.ALL,2)

        #setting up "billboard" button
        self.billboardBox = wx.StaticBox(self.grblPanel, -1, 'Display Live Data')
        self.billboardBox.SetFont(font)
        s40 = wx.StaticBoxSizer(self.billboardBox, wx.HORIZONTAL)
        self.billboardBtn = wx.Button(self.grblPanel, id=wx.ID_ANY, label = "BILLBOARD", size = (75,-1))
        self.billboardBtn.Bind(wx.EVT_BUTTON, getBillboard)
        s40.Add(self.billboardBtn, 0, wx.ALIGN_LEFT, 0)

        #Adding time graph - 25oct20
        self.graphBtn = wx.Button(self.grblPanel, id=wx.ID_ANY, label = "t-graph", size = (75,-1))
        self.graphBtn.Bind(wx.EVT_BUTTON, getGraph)
        s40.Add(self.graphBtn, 0, wx.RIGHT, 0)
        

        #adding type of scan choice - 7 Feb 20
        self.scanLbl = wx.StaticText(self.grblPanel, label = "Scan Type")
        self.scanType = wx.ComboBox(self.grblPanel, choices=self.scanList, value=self.scan, style=wx.CB_READONLY)
        self.Bind(wx.EVT_COMBOBOX, getScan, self.scanType)
        s52 = wx.BoxSizer(wx.VERTICAL)
        s52.Add(self.scanLbl, 0, wx.ALIGN_CENTER_HORIZONTAL, 0)
        s52.Add(self.scanType, 0, wx.ALIGN_CENTER_HORIZONTAL, 0)
        
        #setting up START toggle button with custom bitmap
        self.pulseOn = scale_bitmap(wx.Bitmap("record-button-on.png"), btnSize, btnSize)
        self.pulseOff = scale_bitmap(wx.Bitmap("record-button-off.png"),btnSize, btnSize)
        self.btnLabel = wx.StaticText(self.grblPanel, label="START")
        self.pulseBtn = buttons.GenBitmapToggleButton(self.grblPanel, id=wx.ID_ANY, bitmap=self.pulseOff)
        self.pulseBtn.SetBitmapSelected(self.pulseOn)
        self.pulseBtn.Bind(wx.EVT_BUTTON, getStart)
        s51 = wx.BoxSizer(wx.VERTICAL)
        s51.Add(self.btnLabel, 0, wx.ALIGN_CENTER_HORIZONTAL,0)
        s51.Add(self.pulseBtn, 0, wx.ALIGN_CENTER_HORIZONTAL,0)

        #putting START btn + ScanChoice together
        s50 = wx.BoxSizer(wx.HORIZONTAL)
        s50.Add(s52,0, wx.CENTER,0)
        s50.AddSpacer(20)
        s50.Add(s51,0, wx.CENTER,0)

        #defining labels for grblPanel
        self.grblLabel = wx.StaticText(self.grblPanel, -1, 'XYZ Stage Controls')
        self.grblLabel.SetFont(font)
        self.controlLabel = wx.StaticText(self.grblPanel, -1, 'Data Controls')
        self.controlLabel.SetFont(font)
        
       #putting together all the elements of grblPanel
        grblPnlSizr = wx.BoxSizer(wx.VERTICAL)
        grblPnlSizr.Add(self.grblLabel, 0, wx.CENTER, wx.ALL,2)
        grblPnlSizr.Add(wx.StaticLine(self.grblPanel,), 0, wx.ALL|wx.EXPAND, 5)
        grblPnlSizr.Add(s1, 0, wx.CENTER)
        grblPnlSizr.Add(s2, 0, wx.CENTER)
        grblPnlSizr.Add(s3, 0, wx.CENTER)
        grblPnlSizr.Add(s4, 0, wx.CENTER)
        grblPnlSizr.Add(s5, 0, wx.CENTER)
        grblPnlSizr.Add(s20, 0, wx.CENTER)
        grblPnlSizr.AddSpacer(3)
        grblPnlSizr.Add(self.controlLabel, 0, wx.CENTER)
        grblPnlSizr.Add(wx.StaticLine(self.grblPanel,), 0, wx.ALL|wx.EXPAND, 5)
        grblPnlSizr.Add(s30, 0, wx.CENTER)
        grblPnlSizr.Add(s31, 0, wx.CENTER)
        grblPnlSizr.Add(s32, 0, wx.CENTER)
        grblPnlSizr.AddSpacer(3)
        grblPnlSizr.Add(s40, 0, wx.CENTER)
        grblPnlSizr.AddSpacer(5)
        grblPnlSizr.Add(s50, 0, wx.CENTER)

        self.grblPanel.SetSizer(grblPnlSizr)
        
        self.Layout()
        self.Bind( wx.EVT_CLOSE, self.OnClose )

        graph()

        self.updateStat("",1)

    #----------------------------------------------------------------------

    def updateStat(mf,msg,f):
        if msg == "":
            msg = 'scan' + str(bp.scan) + ' Nb: ' + str(bp.sn)\
                  + '  X' + str(bp.Xtravel) + '  Y' + str(bp.Ytravel) \
                  + '  dX' + str(bp.travelX) + '  dY' + str(bp.travelY) \
                  + '  stp' + str(bp.stepXY) + '  dur' + str(bp.duration)

        mf.statusbar.SetStatusText(msg, f)
        if f != 0:
            mf.statusbar.SetStatusText(V, 0)
        

    #this is not used......
    def save(self,event):
        print ("saving data...")
        self.statusbar.SetStatusText('saving data...', 1)
        header = "Data from MainBeamProfiler"
        saveData(self,header)
        
    def info(self, event):
        """"""
        print ("selected About")
        
    def bkgCor(self, event):
        """"""
        #print "selected bkg"
        if bp.scan == "X" or bp.scan == "Y":
            bkg = dp.CalcBkg(bp.scan, bp.data)
        elif bp.scan == "XY" or bp.scan=="XYZ":
            bkg = dp.CalcBkg(bp.scan, bp.imgData)
        elif bp.scan == "2D":
            #print "Bkg correction does not work on 2D scan data"
            pass
        else:
            print ("Error.......")
            pass
        #print "background value: ", bkg

        #else:
        enterVal = EnterValBkg(self,bkg,bkgStyle)
        enterVal.Show()
        return
        
    def calcCentroid(self, event):
        """"""
        #print "selected centroid"
        if bp.scan == "2D":
            pass
        elif bp.scan == "X" or bp.scan == "Y":
            bp.centroid = dp.calc_centroid(bp.data)
        elif bp.scan == "XY" or bp.scan=="XYZ" :
            bp.centroid = dp.calc_centroid(bp.imgData)
        if bp.Analysis:
            self.calcWidth(event)
        else:
            displayResults = DisplayResults(self)
            displayResults.Show()
        return
        
    def calcWidth(self, event):
        """"""
        #print "selected width"
        if bp.scan == "2D":
            pass
        elif bp.scan == "X" or bp.scan == "Y":
            bp.secMoment = dp.calc_secmom(bp.data)
        elif bp.scan == "XY" :
            bp.secMoment = dp.calc_secmom(bp.imgData)
        print ("Received secMom"),bp.secMoment
        bp.Analysis = False
        displayResults = DisplayResults(self)
        displayResults.Show()
        if bp.BPZ:
            saveBP(self,'')
        return
        
    def dataAnalysis(self, event):
        """"""
        global mf
        #print "selected analysis"
        #this works, but there should be a waiting to enter value of bkg
        bp.resetProcess()
        bp.Analysis = True
        self.bkgCor(event)
        return
        

    #receive value for background subtraction
    def receiveBkg(self, bkg):
        #global imgData, data, dataInput, centroid, secMoment
        global plot, mf, bkgReceived
        #print "received"
        bkgReceived = True
        bkg = float(message)
        #print "new value received: ", bkg

        bp.imgData = dp.subtractBkg(bp.imgData,bkg)
        #reconstructing data to be plotted
        bp.data = dp.rebuildData(bp.imgData, bp.dataInput)
        #updating graph.plot
        graph()

        displayResults = DisplayResults(self)
        displayResults.Show()
        if bp.Analysis:
            self.calcCentroid(event)
        return


    #end scan data acquisition
    def stopScan(self):
        if bp.stp < bp.nsteptot:
            self.statusbar.SetStatusText('!!! scan interrupted !!!', 1)
            #print ("!!!scan interrupted!!!")
            interruptScan(self)
        else:
            #endScan(self)
            self.btnLabel.SetLabel('START')
            self.pulseBtn.SetBitmapSelected(self.pulseOff)
            self.pulseBtn.SetValue(False)
        

    def OnClose(self,event):
        try:
            bp.s.close()
            bp.prop.close()
        except:
            print ("couldnot close s or prop")
        self.Destroy()

#******-------- End of main window frame ------------*********


        
#*****-----Additional frames: BillboardDisplay, ShowImage, DisplayResults, EnterValBkg---
#********************************************************************************

##### Frame to display data value only
class BillboardDisplay(wx.Frame):
    def __init__(self, window_parent ):
        #global iloop, inc
        
        self.chan = int(bp.analogIn)
        #iloop = 12
        #inc = True
        self.timerPeriod = 200

        wx.Frame.__init__(self, window_parent, wx.ID_ANY, "BillBoard - AI" + str(self.chan))
        ico = wx.Icon('OFSI.ico', wx.BITMAP_TYPE_ICO )
        self.SetIcon( ico )

        self.timer = wx.Timer(self)
    
        mainSizer = wx.BoxSizer( wx.VERTICAL )
        panelSizer = wx.BoxSizer( wx.HORIZONTAL )
        self.font = wx.Font(200, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
    
        panel = wx.Panel(self)
        initVal = "0000"
        self.txtValue = wx.StaticText(self, label=initVal)
        self.txtValue.SetFont(self.font)
        self.gaugeMeter = wx.Gauge( self, wx.ID_ANY, 4096, wx.DefaultPosition, \
                        wx.Size( 75,-1 ), wx.GA_VERTICAL|wx.GA_SMOOTH )
        panelSizer.Add(self.txtValue, 0, wx.ALL, 20)
        panelSizer.Add((0,0),1)
        panelSizer.Add(self.gaugeMeter, 0, wx.ALL|wx.EXPAND, 5)
        panel.SetSizer(panelSizer)
        mainSizer.Add(panel, 1, wx.ALL|wx.EXPAND)
        self.SetSizer(mainSizer)
        self.Fit()

        bp.startADC(bp.propPort,bp.propbdr,self.chan,bp.rateVal)
        
        self.Bind(wx.EVT_TIMER, self.updateValue, self.timer)

        #changed from EVT_MOUSE_EVENTS to EVT_MOUSEWHEEL - works fine - FD 04jun18
        #first wheel clik starts, second one stops
        self.Bind( wx.EVT_MOUSEWHEEL, self.startTimer )
        self.Bind( wx.EVT_CLOSE, self.OnClose )

    def startTimer(self,event):
        #print "starting timer....."
        if self.timer.IsRunning():
            self.timer.Stop()
        else:
            self.timer.Start(self.timerPeriod)

    #read ADC and update value on billboard and gauge
    def updateValue(self,event):
        duration = 0.05
        data = bp.readData(duration)
        self.label = "{0:04}".format( data )
        self.txtValue.SetLabel(self.label)
        self.gaugeMeter.SetValue(data)

    def OnClose(self, event):
        #chIdx = int(dataInput[3])
        if self.timer.IsRunning():
            self.timer.Stop()
            #print "stoppped timer "
        try:
            bp.stopADC(self.chan)
            #print "stoppped ADC Chan "
        except:
            print ("Can't close prop")
        self.Destroy()




##### Frame to graph data value in time
#need to add menu options to re-scale plot (both X & Y) and change sampling rate  16nov20
class TimeGraph(wx.Frame):
    def __init__(self, window_parent ):
        
        self.chan = int(bp.analogIn)
        self.timerPeriod = 200
        
        wx.Frame.__init__(self, window_parent, wx.ID_ANY, "Time Graph - AI" + str(self.chan))
        ico = wx.Icon('OFSI.ico', wx.BITMAP_TYPE_ICO )
        self.SetIcon( ico )
        
        # add menubar and menus
        self.menuBar = wx.MenuBar( 0 )
        self.fileMenu = wx.Menu()
        self.SaveMenuItem = self.fileMenu.Append(100,"Save","Save plot data in file")
        self.CloseMenuItem = self.fileMenu.Append(101,"Close","Close Plot Window")
        self.editMenu = wx.Menu()
        self.ScaleMenuItem = self.editMenu.Append(200,"Scale Plot","Change X or Y scale of plot")
        self.SamplingMenuItem = self.editMenu.Append(201,"Sampling","Change sampling rate")
        self.menuBar.Append(self.fileMenu, "File")
        self.menuBar.Append(self.editMenu, "Scale")
        
        # bind items
        self.Bind( wx.EVT_MENU, self.OnSave, self.SaveMenuItem )
        self.Bind( wx.EVT_MENU, self.OnClose, self.CloseMenuItem)
        self.Bind( wx.EVT_MENU, self.OnScale, self.ScaleMenuItem )
        self.Bind( wx.EVT_MENU, self.OnSampling, self.SamplingMenuItem)
        self.SetMenuBar( self.menuBar)
        
        self.DS = False
        self.autoScale = True
        self.t0 = 0
        self.DT = 0
        self.tdat = [(0,0)]
        self.xlabel = "Time (sec)"
        self.ylabel = "Intensity"
        self.ymax = 100
        self.xmax = 2
        self.xRange = (0,self.xmax)
        self.yRange = (0,self.ymax)

        self.plotTitleNS = "Time Plot " + str(self.chan) + " (Not Saved)"
        self.plotTitleDS = "Time Plot " + str(self.chan) + " (Data Saved)"
        
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.updateValue, self.timer)
    
        mainSizer = wx.BoxSizer( wx.VERTICAL )
        
        # add plot
        self.plot = wx.lib.plot.PlotCanvas(self, size=wx.Size(500,300), style=wx.EXPAND)
        self.plot.SetShowScrollbars(True)
        mainSizer.Add(self.plot, 1, wx.EXPAND, 0)
        self.SetSizer(mainSizer)
        self.Fit()

        bp.startADC(bp.propPort,bp.propbdr,self.chan,bp.rateVal)
        self.updateValue(event = None)

        #changed from EVT_MOUSE_EVENTS to EVT_MOUSEWHEEL - works fine - FD 04jun18
        #first wheel clik starts, second one stops
        self.Bind( wx.EVT_MOUSEWHEEL, self.startTimer )
        self.Bind( wx.EVT_CLOSE, self.OnClose )

    def startTimer(self,event):
        #print "starting timer....."
        if self.timer.IsRunning():
            self.timer.Stop()
            self.DT = time.time() - self.t0
            #print ("stop time: "),self.DT
        else:
            self.timer.Start(self.timerPeriod)
            if self.DS:
                self.DS = False
                self.tdat = []
                self.DT = 0
                self.xmax = 2
                self.xRange = ( 0 , self.xmax )
            if self.DT == 0:
                self.t0 = time.time()
            else:
                self.t0 = time.time() - self.DT

    #read ADC and update graph
    def updateValue(self,event):
        duration = 0.05
        datval = bp.readData(duration)
        if datval > self.ymax and self.autoScale:
            self.ymax = 1.2 * datval
            self.yRange = (0,self.ymax)
        dt = time.time() - self.t0
        if dt > self.xmax:
            self.xmax = 5 * self.xmax
            self.xRange = ( 0 , self.xmax )
        datpt = (dt , datval)
        self.tdat.append(datpt)
        self.updateGraph(self.tdat,self.xRange, self.yRange)
         
    def updateGraph(datlist, xrange, yrange):
        lineData = datlist
        line = wx.lib.plot.PolyLine(lineData, colour='red', width=2)
        if self.DS:
            self.plotTitle = self.plotTitleDS
        else:
            self.plotTitle = self.plotTitleNS
        pg = wx.lib.plot.PlotGraphics([line], self.plotTitle, self.xlabel, self.ylabel)
        #print "---graphing -- -- ",plotTitle
        self.plot.Draw(pg, self.xRange, self.yRange)
        
    def OnScale(self, event):
        #re-scale axes of graph plot
        dlg = wx.TextEntryDialog(self,"Enter new value",'0,100,0,100')
        dlg.ShowModal()
        if dlg.ShowModal() == wx.ID_OK :
            newScale = dlg.GetValue()
            #need to add code to parse xr and yr from newScale string
            self.autoScale = False
        else:
            self.autoScale = True
            xr = self.xRange
            yr = self.Yrange
        self.updateGraph(self.tdat,xr, yr)
        pass
  
    def OnSampling(self, event):
        #change sampling rate - change/recalculate value of self.timePeriod
        #need to set-up dialog entry
        if self.timer.IsRunning():
            self.timer.Stop()
            self.DT = time.time() - self.t0
        newRate = wx.TextEntryDialog(self,"Enter New Sampling Rate (/s)",'200')
        newRate.ShowModal()
        self.timerPeriod = newRate.GetValue()
        #need to check/validate value
        pass


    def OnClose(self, event):
        #chIdx = int(dataInput[3])
        if self.timer.IsRunning():
            self.timer.Stop()
            #print "stoppped timer "
        try:
            bp.stopADC(self.chan)
            #print "stoppped ADC Chan "
        except:
            print ("Can't close prop")
        self.Destroy()

    def OnSave(self,event):
        global mf
        writeData = self.tdat
        if len(writeData) > 0 :
            filetypes = "CSV files (*.csv)|*.csv|Text files (*.txt)|*.txt|All files|*"
            dlg = wx.FileDialog(frame,"Choose a file", style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT, wildcard=filetypes)
            outFile = None
            
            if dlg.ShowModal()==wx.ID_OK:
                try:
                    filename=dlg.GetFilename()
                    dirname=dlg.GetDirectory()
                    fullPath = os.path.join(dirname, filename)
                    date = '"' + time.asctime() + '"'
                    title = "saving data"
                    
                    dlg2 = wx.TextEntryDialog(frame, 'Enter some text','Text Entry')
                    dlg2.SetValue("")
                    if dlg2.ShowModal() == wx.ID_OK:
                        comment = dlg2.GetValue()
                        print('You entered: %s\n' % comment)
                    dlg2.Destroy()

                    print ("finename fullPath: "), fullPath

                    outFile = open(fullPath, "w")
                
                    # write header info
                    outFile.write( date )
                    outFile.write( "\n" )

                    # write comment info
                    outFile.write( comment )
                    outFile.write( "\n" )

                    # write data info
                    outFile.write( "sec,val" + "\n"  )

                    #write data
                    nData = len(writeData)

                    print ("info..."), comment
                    print ("data:"),writeData
                    strfmt = ''
                    

                    for nn in range(nData):
                        strfmt = str(writeData[nn][0]) + ','
                        strfmt = strfmt + str(writeData[nn][1]) + "\n"
                        outFile.write(strfmt)
                        
                    outFile.close()
                    print ("finished writing data in file")

                
                except IOError as e:
                    mf.updateStat('IOError', 0)
                    print ("Error opening file"), e
                except ValueError as e:
                    mf.updateStat('ValueError', 0)
                    print ("Error writing file"), e
                except:
                    mf.updateStat('Error saving', 0)
                    print ("Error in saving data")
                    outFile.close()

        self.DS = True
        self.updateValue(event = None)
        pass




###----Frame to display image of 2Dscan
class showImage(wx.Frame):
    def __init__(self, title = "BP_IMG " + str(bp.sn)):
        wx.Frame.__init__(self, None , -1, title, size=(225,245))

        sm0 = "Scan # " + str(bp.sn)
        sm1 = "Z = " + str(bp.travelZ) + ".." + str(bp.Xtravel) + "x" + str(bp.Ytravel)

        #creating a status bar with 2 fields to display messages
                                                    
        self.statusbar = self.CreateStatusBar(2)
        self.statusbar.SetStatusWidths([panelWidth, -1])
        self.statusbar.SetStatusText(sm0 , 0)
        self.statusbar.SetStatusText(sm1 , 1)

        mydata = np.asarray(bp.imgData)
        mydata = np.transpose(mydata)
        #note 23jun20-img is transposed, vertical is X and horizontal is Y
        #w/ transposition, it now matches X & Y, but Y is inverted
        #w/ flip, it is correct orientation
        #print "mydata array:"
        #print mydata
        h = mydata.shape[0]
        w = mydata.shape[1]
        f = int( 400 / w )
        #subtract bkg
        bp.bkg = np.amin(mydata)
        mydata = mydata - bp.bkg
        #re-orient the image to match real space
        mydata = np.flip(mydata,0)
        #scale to 255 max
        #defining vmax as a float, all following values are also float (decimals)
        vmax = float(np.amax(mydata))
        scale = 1.00001
        if vmax > 255:
            scale = (vmax / 255.000) * 100
            #print "vmax = ", vmax, "  scaling : ", scale, vmax/255
            mydata = ( mydata * 100 ) / scale
        else:
            scale = (255.000 / vmax) * 100
            #print "vmax = ", vmax, "  scaling : ", scale
            mydata = ( mydata * scale ) / 100
        #print "mydata scaled array:"
        #print mydata
        mydata = np.floor(mydata)
        mydata = mydata.astype(int)
        
        npimg = Image.fromarray(mydata).resize((f*w,f*h),resample=3, box=None)

        #npimg.show()
        #this shows the actual and correct picture - 16apr20/FD
        
        databmp = ic.WxBitmapFromPilImage(npimg)

        panel = wx.Panel(self,-1)
        btn = wx.BitmapButton(panel,-1,databmp,pos=(0,0))
        btn.SetDefault()




####----Frame to display results
class DisplayResults(wx.Frame):
    def __init__(self, parent):
        wx.Frame.__init__(self, parent, title="BP X0&FW4S_Z=" + str(bp.travelZ))


        smr0 = "Scan # " + str(bp.sn)
        smr1 = "Z = " + str(bp.travelZ) + ".." + str(bp.Xtravel) + "x" + str(bp.Ytravel)

        #creating a status bar with 2 fields to display messages
        self.statusbar = self.CreateStatusBar(2)
        self.statusbar.SetStatusWidths([panelWidth, -1])
        self.statusbar.SetStatusText(smr0 , 0)
        self.statusbar.SetStatusText(smr1 , 1)

        
        titleFont = wx.Font(20, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        resultsFont = wx.Font(16, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        
        panel = wx.Panel(self)

        Xc = int(bp.centroid[0]*1000) / 1000

        # Creating widget Boxes to display results 
        xAxisBox = wx.StaticBox(panel,-1,'X-Axis')
        yAxisBox = wx.StaticBox(panel,-1,'Y-Axis')
        xAxisBox.SetFont(titleFont)
        yAxisBox.SetFont(titleFont)

        xCenter = wx.StaticText(panel, -1, 'X0: ' + str(round(bp.centroid[0],3)))
        yCenter = wx.StaticText(panel, -1, 'Y0: ' + str(round(bp.centroid[1],3)))
        xCenter.SetFont(resultsFont)
        yCenter.SetFont(resultsFont)

        xWidth = wx.StaticText(panel, -1, 'FWx: ' + str(round(bp.secMoment[0],3)))
        yWidth = wx.StaticText(panel, -1, 'FWy: ' + str(round(bp.secMoment[1],3)))
        xWidth.SetFont(resultsFont)
        yWidth.SetFont(resultsFont)

        # Starts of sizers section
        sizerX = wx.StaticBoxSizer(xAxisBox, wx.VERTICAL)
        sizerY = wx.StaticBoxSizer(yAxisBox, wx.VERTICAL)
        mainSizer = wx.BoxSizer(wx.HORIZONTAL)
        
        sizerX.Add(xCenter, 0, wx.LEFT, 10)
        sizerX.Add(xWidth, 0, wx.LEFT, 10)
        sizerY.Add(yCenter, 0, wx.LEFT, 10)
        sizerY.Add(yWidth, 0, wx.LEFT, 10)
        mainSizer.Add(sizerX,1,wx.EXPAND|wx.ALL,20)
        mainSizer.Add(sizerY,1,wx.EXPAND|wx.ALL,20)
        
        panel.SetSizer(mainSizer)
        
    def OnClose(self, event):
        self.Destroy()


####----Frame to enter bkg value
class EnterValBkg(wx.Frame):
    def __init__(self, parent, bkg, style):
        wx.Frame.__init__(self, parent,
                          title='Enter Background Value',
                          size = (220,130), style = style)
        
        global newBkg
        newBkg = bkg
        #print "default bkg value: ", bkg

        self.panel = wx.Panel(self)
        titleFont = wx.Font(20, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        resultsFont = wx.Font(16, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)

        #bkg value entry box
        self.bkgLabel = wx.StaticText(self.panel, wx.ID_ANY, 'Bkg Value')
        self.bkgVal = wx.TextCtrl(self.panel, wx.ID_ANY,str(bkg),style=wx.TE_PROCESS_ENTER)
        self.bkgVal.Bind(wx.EVT_TEXT_ENTER, self.getBkg)
        
        #confirm entry box with 2 buttons
        self.okBtn = wx.Button(self.panel,-1,"OK") 
        self.okBtn.Bind(wx.EVT_BUTTON, self.okClick) 
        self.cancelBtn = wx.Button(self.panel,-1,"Cancel") 
        self.cancelBtn.Bind(wx.EVT_BUTTON, self.cancelClick) 

        #sizer widget for entry box
        szr1 = wx.BoxSizer(wx.HORIZONTAL)
        szr1.Add(self.bkgLabel, 0, wx.ALL,5)
        szr1.Add(self.bkgVal, 0, wx.ALL,5)

        #sizer widget for confirm choice
        szr2 = wx.BoxSizer(wx.HORIZONTAL)
        szr2.Add(self.okBtn, 0, wx.ALL,5)
        szr2.Add(self.cancelBtn, 0, wx.ALL,5)
        
        #sizer widget for complete panel window
        mainSzr = wx.BoxSizer(wx.VERTICAL)
        mainSzr.Add(szr1,1,wx.EXPAND|wx.ALL,8)
        mainSzr.Add(szr2,1,wx.EXPAND|wx.ALL,8)
        
        self.panel.SetSizer(mainSzr)

    # Function to capture the value
    def getBkg(self,event):
        global newBkg
        newBkg = int(self.bkgVal.GetValue())
        #print "New bkg value: ", newBkg

    # Function to confirm the value
    def okClick(self,event):
        global newBkg, mf
        bp.bkg = newBkg
        #print "Value Confirmed! ", bp.bkg
        
        if bp.scan == "X" or bp.scan == "Y":
            bp.data = dp.subtractBkg(bp.scan, bp.data, bp.bkg)
        elif bp.scan == "XY" or bp.scan == "2D":
            bp.imgData = dp.subtractBkg(bp.scan, bp.imgData, bp.bkg)
            #reconstructing data to be plotted
            bp.data = dp.rebuildData(bp.imgData, bp.stepXY)
        graph()
        if bp.Analysis:
            mf.calcCentroid(event)
        self.Destroy()


    # Function to cancel the value
    def cancelClick(self,event):
        self.Destroy()
   
    def OnClose(self, event):
        self.Destroy()

#****----- End of additional frames-----------------------
#************************************************************************
#************************************************************************



###-----  function to define graphing of data --------------
        #still needs to be updated
def graph():  #plot is the panel on which the PlotCanvas is defined
    global plot, mf
    data0 = []
    scan = bp.scan
    stp = bp.stp
    step = bp.stepXY
    nPoints = len(bp.data)
    nstepX = bp.nstepX
    nstepY = bp.nstepY
    nsteptot = bp.nsteptot
    maxY = 1

    if bp.dataSaved :
        ds = "(SAVED)"
    else:
        ds = '(NOT saved)'
    
    if scan == "Y":
        travel = bp.Ytravel
    else:
        if bp.Ytravel > bp.Xtravel:
            travel = bp.Ytravel
        else:
            travel = bp.Xtravel
        
    print ("*** stp: "), stp,  "*** nPoints: ", nPoints
    
    if scan == '2D':
        Ystp = bp.stp % nstepX
        #print "graph 2D Y-stp: ", Ystp

    #find the max value
    for n in range(nPoints):
        if bp.data[n][1] > maxY:
            maxY = bp.data[n][1] * 1.1           
    #defining plotting axis ranges    
    xRange = (0, travel)
    yRange = (bp.minVal, maxY )
    
    #defining plot for Xscan
    if scan == "X":
        plotTitle = "Plot X-axis " + ds
        line = wx.lib.plot.PolyLine(bp.data, colour='red', width=2)
        pg = wx.lib.plot.PlotGraphics([line], plotTitle, bp.xlabel, bp.ylabel)
   
    #defining plot for Yscan
    if scan == "Y":
        plotTitle = "Plot Y-axis " + ds
        line = wx.lib.plot.PolyLine(bp.data, colour='red', width=2)
        pg = wx.lib.plot.PlotGraphics([line], plotTitle, bp.xlabel, bp.ylabel)

    #defining plot for XYscan
    if scan == "XY" or scan=="XYZ":
        if stp < nstepX + 2:
            plotTitle = "Plot X-axis " + ds
            line = wx.lib.plot.PolyLine(bp.data, colour='red', width=2)
            pg = wx.lib.plot.PlotGraphics([line], plotTitle, bp.xlabel, bp.ylabel)
        elif stp < nsteptot :
            plotTitle = "Plot Y-axis " + ds
            line = wx.lib.plot.PolyLine(bp.data, colour='blue', width=2)
            pg = wx.lib.plot.PlotGraphics([line], plotTitle, bp.xlabel, bp.ylabel)
        else:
            for n in range(nstepX + 1):
                dv = bp.imgData[n][0]
                if dv > maxY:
                    maxY = dv * 1.1
                yRange = (bp.minVal, maxY )
                travel0 = step * n
                dataPoint0 = (travel0,dv)
                data0.append(dataPoint0)
            line0 = wx.lib.plot.PolyLine(data0, colour='red', width=1)
            plotTitle = "Plot X(red) & Y(blue) " + ds
            line = wx.lib.plot.PolyLine(bp.data, colour='blue', width=1)
            pg = wx.lib.plot.PlotGraphics([line]+[line0], plotTitle, bp.xlabel, bp.ylabel)
            
    #defining plot for 2Dscan
    if scan == "2D":
        plotTitle = "Plot 2D X-axis 0/" + str(bp.nstepY + 1) + ds
        if stp < nstepX + 1:
            line = wx.lib.plot.PolyLine(bp.data, colour='red', width=2)
            pg = wx.lib.plot.PlotGraphics([line], plotTitle, bp.xlabel, bp.ylabel)
        elif stp < nsteptot + 1:
            ystp = int(math.floor(bp.stp / bp.nstepX))
            xstp = bp.stp % bp.nstepX 
            plotTitle = "Plot 2D X-axis " + str(ystp) + "/" + str(bp.nstepY + 1) + ds
            line = wx.lib.plot.PolyLine(bp.data, colour='blue', width=2)
            pg = wx.lib.plot.PlotGraphics([line], plotTitle, bp.xlabel, bp.ylabel)


    #print "---graphing -- -- ",plotTitle
    plot.Draw(pg, xRange, yRange)
    
###-----  End of graphing data function --------------
       





### --- Starting scan: moving stage and acquiring data
def startScan(self):
    global mf
    mf = self
    #print "startscan self mf:", mf
    #initializing all variables
    mf.statusbar.SetStatusText('starting scan...', 1)
    bp.updateSteps()
    bp.resetData()
    bp.dataSaved = False
    
    if bp.BPZ:
        bp.scan = "XY"

    propPort = bp.propPort
    chIdx = int(bp.analogIn)
    grblPort = bp.grblPort
    travelStep = bp.stepXY
    duration = bp.duration
    scan = bp.scan
    nstepX = bp.nstepX
    nstepY = bp.nstepY
    nsteptot = bp.nsteptot
    Xtravel = bp.Xtravel
    Ytravel = bp.Ytravel
    stepXY = bp.stepXY
    nsteptot = bp.nsteptot
    
    
    #bp.travelX = 0
    #bp.travelY = 0
    
    minVal = 0
    maxVal = 1

    #check and validate all input data
    try:
        ii = 0
        for dat in [chIdx,grblPort,travelStep,Xtravel,Ytravel,\
                    duration,propPort,scan,nsteptot]:
            #print dat
            if dat == 0 and ii != 0:
                raise ValueError
            ii += 1
        if not Xtravel > stepXY:
            #print "error: travel NOT> step"
            raise ValueError
    except ValueError:
        print ("invalid datainput")
        mf.statusbar.SetStatusText('invalid data... end scan', 1)
        endScan(mf)

    #making sure that the Arduino-grbl is initialized
    try:
        if bp.s is None:
            #print "bp.s is none"
            startArduino(bp.grblPort, bp.grblbdr)
        else:
            #print "bp.s is NOT none"
            if not bp.s.isOpen():
                #print "bp.s is NOT open"
                bp.s.open()
    except:
        #print ("exception - starting Arduino...")
        #print "port: ", bp.grblPort, "DataRate dr: ", bp.grblbdr
        startArduino(bp.grblPort, bp.grblbdr)

    #set current position as home
    bp.s.write(" G92 X0 Y0 \r \n")
    bp.s.write(" G91 F1000 \r \n")

    #move to edge start of scan (YES - FD-9jan20)----
    #print "travelling to edge of Scan X"
    #print "totalTravel: ", totalTravel
    travelEdgeX = ((nstepX) * 0.5) * travelStep + 1
    travelEdgeY = ((nstepY) * 0.5) * travelStep + 1
    #print "travelEdge: ", travelEdgeX

    mf.updateStat('parameters valid',0)

    #print "travelXedge: ", travelXedge
    if scan == "X" or scan == "XY" or scan == "XYZ":
        bp.s.write(str('G01 X-' + str(travelEdgeX) + '\r \n'))
        bp.s.write(str('G01 F' + str(bp.travelSpeed) + ' X1 \r \n'))
        time.sleep((travelEdgeX * 1.2)/bp.travelSpeed + 1)
    elif scan == "Y":
        bp.s.write(str('G01 Y-' + str(travelEdgeY) + '\r \n'))
        bp.s.write(str('G01 F' + str(bp.travelSpeed) + ' Y1 \r \n'))
        time.sleep((travelEdgeY * 1.2)/bp.travelSpeed + 1)
        pass
    elif scan == "2D":
        bp.s.write(str('G01 X-' + str(travelEdgeX) + 'Y-' + str(travelEdgeY) + '\r \n'))
        bp.s.write(str('G01 F' + str(bp.travelSpeed) + 'X1 Y1 \r \n'))
        time.sleep(((travelEdgeX + travelEdgeY) * 1.2)/bp.travelSpeed + 1)
        pass
    else:
        print ("error")
        mf.updateStat('scan type error',1)
        pass
    #print "ready to start data acquisition"
    ###################***********************

    #starting the ADC channel on DataSpider / propcom
    bp.startADC(bp.propPort,bp.propbdr,chIdx,bp.rateVal)
    time.sleep(0.1)
    
    #read and delete first data to clear all buffers - added 20jan20
    datVal = bp.readData(duration)
    datVal = 0
    del bp.data[:]
    bp.stp = 0
    bp.scanning = True

    self.updateStat('taking data',0)

    #print "starting dataAcquisition...."
    #use a timer to initiate each data reading
    self.Bind(wx.EVT_TIMER, takeData, self.stepTimer)
    stepDelay = (0.1 + (stepXY*60/bp.travelSpeed))*1000
    stepPeriod = int(duration*1000 + stepDelay)
    bp.stp = 0
    #print "start timer self:", self
    mf.stepTimer.Start(stepPeriod,wx.TIMER_CONTINUOUS)
    

def takeData(self):
    #print "take data self:", self
    global plot, mf
    if bp.scanning:
        if bp.stp == 0:
            #print "deleting data"
            del bp.data[:]
            del bp.imgData[:]
        
        travel = bp.stepXY * bp.stp
        #read data value
        datVal = bp.readData(bp.duration)
        dataPoint = (travel,datVal)
        #print "scanning......",bp.scan,"...", bp.scanning
        mm = 'scanning...' + str(bp.scan)
        mf.statusbar.SetStatusText(mm, 1)
        
        #-----XY scan-------------------------------------
        #if X and Y are mdifferent, we need to "padd" the shorter axis 11apr20
        if bp.scan == "XY":
            #print "scanning XY...stp",bp.stp,"...of...X",bp.nstepX,"...Y",bp.nstepY
            ystp = bp.stp - bp.nstepX - 1

            if bp.stp == 0:
                bp.imgData = [[datVal]]
                bp.data.append(dataPoint)
                bp.s.write(bp.gcodeTravelX)
                bp.stp += 1
                pass
                
            if bp.stp < bp.nstepX :
                #print "Scanning X of XYScan: ", bp.stp," of..",bp.nstepX
                bp.data.append(dataPoint)
                bp.imgData.append([datVal])
                bp.s.write(bp.gcodeTravelX)
                bp.stp += 1
                pass
                
            elif bp.stp == bp.nstepX :
                #print "last X datapoint stp: ", bp.stp, "data: ", dataPoint
                bp.data.append(dataPoint)
                bp.imgData.append([datVal])
                gcodeTravelNext = "G01 F1000 X-" + str(bp.travelCenterX) +\
                                    " Y-" + str(bp.travelCenterY) + '\r \n'
                bp.s.write(str(gcodeTravelNext))
                time.sleep( ( ( bp. travelCenterX + bp.travelCenterY) * 0.9) / bp.travelSpeed + 1)
                gcodeTravelStart = "G01 F" + str(bp.travelSpeed) + " X1 Y1" + '\r \n'
                bp.s.write(str(gcodeTravelStart))
                time.sleep(((2) * 1.2)/bp.travelSpeed + 1)
                bp.stp += 1
                    
            elif ystp == 0:
                #print "Starting Yscan of XY  ...stp: ", bp.stp, "data: ", dataPoint
                del bp.data[:]
                dataPoint = ( ystp * bp.stepXY, datVal )
                bp.data.append(dataPoint)
                bp.imgData[ystp].append(datVal)
                bp.s.write(str(bp.gcodeTravelY))
                bp.stp += 1

            elif ystp > 0 and ystp < bp.nstepY:
                dataPoint = ( ystp * bp.stepXY, datVal )
                bp.data.append(dataPoint)
                
                if ystp > bp.nstepX:
                    bp.imgData.append([0])
                    bp.imgData[ystp].append(datVal)
                    pass
                else:
                    bp.imgData[ystp].append(datVal)
                    
                bp.s.write(str(bp.gcodeTravelY))
                bp.stp += 1
                
            elif ystp == bp.nstepY :
                #print "last Y data point....."
                dataPoint = ( ystp * bp.stepXY, datVal )
                bp.data.append(dataPoint)
                if ystp > bp.nstepX:
                    bp.imgData.append([0])
                    bp.imgData[ystp].append(datVal)
                    pass
                else:
                    bp.imgData[ystp].append(datVal)
                #bp.s.write(str(bp.gcodeTravelY))
                bp.scanning = False

            mm = mm + ' step  ' + str(bp.stp) + ' of ' + str(bp.nstepX+bp.nstepY)
            mf.updateStat(mm, 1)
            
            graph()

            if bp.BPZ:
                mf.dataAnalysis
                
            pass



        #---X-scan------------------------------------
        elif bp.scan == "X":
            #print "scanning X ...stp: ", bp.stp, "  out of nsteptot: ", bp.nsteptot
            bp.data.append(dataPoint)
            bp.imgData.append(datVal)
            if bp.stp == bp.nsteptot:
                bp.scanning = False
                #print "completed X-scan..", bp.scanning
            else:    
                bp.s.write(str(bp.gcodeTravelX))
                bp.stp += 1
            mm = mm + ' step  ' + str(bp.stp) + ' of ' + str(bp.nstepX+bp.nstepY)
            mf.updateStat(mm, 1)
            
            graph()
            pass


        #---Y-scan------------------------------------
        elif bp.scan == "Y":
            #print "scanning Y"
            bp.imgData.append(datVal)
            bp.data.append(dataPoint)
            if bp.stp == bp.nsteptot:
                #print "completed X-scan"
                bp.scanning = False
            else:    
                bp.s.write(str(bp.gcodeTravelY))
                bp.stp += 1
            mm = mm + ' step  ' + str(bp.stp) + ' of ' + str(bp.nstepX+bp.nstepY)
            mf.updateStat(mm, 1)
            
            graph()
            pass
        

        #---2D-scan------------------------------------
        elif bp.scan == "2D":
            #print "scanning 2D"
            
            if bp.stp == bp.nstepX or bp.stp > bp.nstepX:
                ystp = int(math.floor(bp.stp / bp.nstepX))
                
            ystp = int(math.floor(bp.stp / (bp.nstepX + 1)))
            xstp = bp.stp % (bp.nstepX + 1)
            #print "new 2Dscan xstp & ystp: ", xstp,"-of-",bp.nstepX\
                        #,"--", ystp , "-of-" ,bp.nstepY
            
                
            if bp.stp < bp.nstepX :
                ystp = 0
                xstp = bp.stp

            if ystp < bp.nstepY + 1:
                
                if xstp == 0:
                    #print "deleting data..xstp: ", xstp
                    del bp.data[:]
        
                #print "X-scan in 2Dscan....",xstp,"-of-",bp.nstepX
                travelX = bp.stepXY * xstp
                dataPoint = (travelX,datVal)
                bp.data.append(dataPoint)
                
                if ystp == 0:
                    if xstp == 0:
                        bp.imgData = [[datVal]]
                    else:
                        bp.imgData.append([datVal])
                else:
                    bp.imgData[xstp].append(datVal)
                    

                mm = mm + ' step  ' + str(bp.stp) + ' of ' + str(bp.nstepX+bp.nstepY)
                mf.updateStat(mm, 1)
            
                graph()
                

                if xstp == bp.nstepX and ystp < bp.nstepY:
                    #print "completed X-scan"
                    #goback on X to edge of X-scan
                    travelBack = travelX + 1
                    #print "travelBack: ", travelBack
                    bp.s.write(str('G01 F1000 X-' + str(travelBack) + '\r \n'))
                    time.sleep(((travelBack) * 0.9)/bp.travelSpeed + 1)
                    bp.s.write(str('G01 F' + str(bp.travelSpeed) + ' X1 \r \n'))
                    time.sleep(((1) * 1.2)/bp.travelSpeed + 0.5)
                    if ystp < bp.nstepY:
                        #print "travelNextYstp: ", bp.gcodeTravelY
                        bp.s.write(str(bp.gcodeTravelY))
                        time.sleep(0.2)
                    bp.stp += 1

                elif xstp < bp.nstepX and ystp < bp.nstepY + 1:
                    bp.s.write(str(bp.gcodeTravelX))
                    bp.stp += 1
                
                elif xstp == bp.nstepX and ystp == bp.nstepY:
                    #print "end of 2D scan"
                    bp.scanning = False

            else:
                bp.scanning = False

            pass #end of 2Dscan
                               

        #---XYZ-scan------------------------------------
        elif bp.scan == "XYZ":           #added started  FD-31oct20
            #print ("scanning XYZ")
            pass
            

        else:
            print ("No Scan Selected")
            pass
    
    else:
        #print "MAX stp reached", bp.stp, "of ", bp.nsteptot,"...STOP SCANNING"

        #move back to center of field
        #print "travelling to center"
        mf.statusbar.SetStatusText('END OF SCAN... Moving back to center', 1)
        
        bp.s.write("G90 G0 X0 Y0 \r \n ")
        bp.s.write('G91 F' + str(bp.travelSpeed) + ' \r \n ')
        time.sleep(1)

        #print "end of scanning....",bp.scanning
        endScan(mf)


def endScan(mf):
    #print "emdscan self:", mf
    try:
        mf.stepTimer.Stop()
        #print "......... Timer Stopped!!........"
    except:
        print ("error trying to stop timer...")
        pass
    mf.btnLabel.SetLabel('START')
    mf.pulseBtn.SetBitmapSelected(mf.pulseOff)
    mf.pulseBtn.SetValue(False)
    mm = 'end scan'
    mf.updateStat(mm, 0)
    mf.updateStat('',1)
    print ("my data:"), bp.imgData
    graph()
    if bp.scan == "2D":
        #print "calling 2Dimage"
        viewImage = showImage()
        viewImage.Show()
    elif bp.BPZ:
        mf.dataAnalysis(event = None)
    pass



def interruptScan(self):
    global mf
    """
Function called when scan has been interrupted.
Need to stop Arduino grbl, stop stages, and come nack to original position
    """

    mm = '!!scan interupted!!'
    mf.updateStat(mm, 1)
    
    #send command to Arduino to stop (pause)
    bp.s.write("! \r \n ")
    time.sleep(0.2)
    bp.s.write("~ \r \n ")

    #move back to center of field
    #print "travelling to center"
        
    mm = 'moving back center'
    mf.updateStat(mm, 0)
    
    bp.s.write("G90 G0 X0 Y0 \r \n ")
    bp.s.write('G91 F' + str(bp.travelSpeed) + ' \r \n ')
    time.sleep(1)
    
    #stopArduino()
    #bp.stopADC(bp.analogIn)

    endScan(self)
    pass
        
    

#------Functions specific to grbl-Arduino--------------------------------
#waking-up Arduino
def startArduino(grblPort, grblbdr):
    gcode =  "$I"   #asking grbl for built info

    # Open serial port
    try:
        if bp.s is None:
            pass
            bp.s = serial.Serial(bp.grblPort,bp.grblbdr)
            bp.s.timeout = 1
        else:
            if not bp.s.isOpen():
                pass
                bp.s = serial.Serial(bp.grblPort,bp.grblbdr)
                bp.s.timeout = 1
    except NameError:
        pass
        bp.s = serial.Serial(bp.grblPort,bp.grblbdr)
        bp.s.timeout = 1

    # Wake up 
    bp.s.write("\r\n\r\n") # Hit enter a few times to wake the Printrbot
    #print "waking up arduino"
    time.sleep(1)   # Wait for Arduino to initialize
    bp.s.flushInput()  # Flush startup text in serial input
    #sending string l to grbl
    bp.s.write(gcode + '\n') # Send g-code block
    #print "sent: ",gcode
    nb = bp.s.inWaiting()
    #print "Nb Bytes: ",nb
    #print "receiving response from arduino..",
    grbl_out = bp.s.readline() # Wait for response - read only first line
    #print ' : ' + grbl_out.strip()
    #setting travel speed and relative coordinates
    bp.s.write('G91 F' + str(bp.travelSpeed) + ' \r \n ')
    bp.s.write('G01 X-1 \r \n')
    bp.s.write('G01 X1 \r \n')
    time.sleep(0.5)
 
#sending G-code to Arduino
def sendCode(gcode):
    bp.s.write(str(gcode))
    bp.s.write('\r \n')
    time.sleep(0.05)

# closing serial port "s" to Arduino
def stopArduino():
    try:
        if bp.s.isOpen():
            bp.s.close()
            #print "grblComPort is closed."
        else:
            print ("s is already clsoed")
    except:
        print ("error trying to close s")
    
    
    
#------End of grbl-Arduino--------------------------------




#helper function -------
def scale_bitmap(bitmap, width, height):
    image = wx.ImageFromBitmap(bitmap)
    image = image.Scale(width, height, wx.IMAGE_QUALITY_HIGH)
    result = wx.BitmapFromImage(image)
    return result


def saveData(frame,header):
    #global data, dataInput, imgData, totalTravel, duration, travelStep, centroid, secMoment
    global mf
    totalTravel = bp.dataInput[2]
    travelStep = bp.stepXY
    nstepX = bp.nstepX
    nstepY = bp.nstepY
    travelZ = bp.travelZ
    scan = bp.scan
    sn = bp.sn
    duration = bp.duration
    imgData = bp.imgData
    data = bp.data
    bkg = bp.bkg
    BPZ = bp.BPZ
    centroid = bp.centroid
    secMoment = bp.secMoment
    nsteptot = bp.nsteptot
    #print "saving.....duration: ", duration,"str..: ", str(duration),\
          #"..scan..",scan

    if scan == "X" or scan == "Y":
        #print "...saving...scan:",scan
        writeData = data
        #rint "...saving....1st data: ",writeData[0]
        
    if scan == 'XYZ':
        writeData = BPZ
    else:
        writeData = imgData

    if len(writeData) > 0 :
        filetypes = "CSV files (*.csv)|*.csv|Text files (*.txt)|*.txt|All files|*"
        dlg = wx.FileDialog(frame,"Choose a file", style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT, wildcard=filetypes)
        outFile = None
        if dlg.ShowModal()==wx.ID_OK:
            try:
                filename=dlg.GetFilename()
                dirname=dlg.GetDirectory()
                fullPath = os.path.join(dirname, filename)
                date = '"' + time.asctime() + '"'
                title = "saving data"
                #SetTitle( title + " - " + filename )

                dlg2 = wx.TextEntryDialog(frame, 'Enter some text','Text Entry')
                dlg2.SetValue("")
                if dlg2.ShowModal() == wx.ID_OK:
                    comment = dlg2.GetValue()
                    print('You entered: %s\n' % comment)
                dlg2.Destroy()

                outFile = open(fullPath, "w")
                
                # write header info
                outFile.write( date )
                outFile.write( "\n" )

                outFile.write( '"' + header + '"' )
                outFile.write( "\n" )

                outFile.write( "Scan: ," + scan )
                outFile.write( ",Nb: ," + str(sn) )
                outFile.write( "\n" )

                #should insert branch for XYZ scan  FD-31oct20
                
                outFile.write( "Step:," + str(travelStep) )
                outFile.write( ",Duration:," + str(duration) )
                outFile.write( "\n" )

                outFile.write( "Zposition: ," + str(travelZ) )
                outFile.write("\n")

                outFile.write( "XYcenters: ," + str(centroid[0]) )
                outFile.write( "," + str(centroid[1]) )
                outFile.write("\n")

                outFile.write( "XY FW4S: ," + str(secMoment[0]) )
                outFile.write( "," + str(secMoment[1]) )
                outFile.write("\n")


                # write data - define nb of columns in imgData
                # depends on scan
                nData = len(writeData)
                print ("***saving len imgData.....:"), nData,"data..",writeData[nData-1]
                
                if scan == "X" or scan == "Y":
                    cols = 2
                elif scan == "2D":
                    #print "saving 2D ncols:", bp.nstepX
                    cols = bp.nstepX
                else:
                    cols = 3

                #print "***saving....scan..",scan,"....ncols..", cols
                
                for n in range(cols):
                    #print "saving data...list row index n: ", n
                    if n == 0 and scan != "2D":
                        strfmt = str('mm,')
                        
                    elif n == 1 and scan == "X":
                        strfmt = str('X,')
                        
                    elif n == 1 and scan == "XY":
                        strfmt = str('X,')

                    elif n == 1 and scan == "Y":
                        strfmt = str('Y,')
                        
                    elif n == 2 and scan == "XY":
                        print "col :",n,"   scan : ", scan
                        strfmt = str('Y,')
                        
                    else:
                        strfmt = ""

                    #print "saving col :", n
                    #print "initial string to be saved :", strfmt
                        
                    for nn in range(nData):
                        try:
                            if nn == nData - 1:
                                if scan == "2D":
                                    strfmt = strfmt + str(writeData[nn][n]) + str('\n')
                                elif scan == "X" or scan == "Y":
                                    strfmt = strfmt + str(writeData[nn][n]) + "\n"
                                elif n == 0:
                                    strfmt = strfmt + str(nn * travelStep) + "\n"
                                else:
                                    strfmt = strfmt + str(writeData[nn][n - 1]) + "\n"

                            else:
                                if scan == "2D":
                                    strfmt = strfmt + str(writeData[nn][n]) + str(',')
                                elif scan == "X" or scan == "Y":
                                    strfmt = strfmt + str(writeData[nn][n]) + ","
                                elif n == 0:
                                    strfmt = strfmt + str(nn * travelStep) + ","
                                else:
                                    strfmt = strfmt + str(writeData[nn][n - 1]) + ","
                                    
                        except IndexError:
                            print ("index error - ignored.."),nn,"//",n
                            pass
                    outFile.write(strfmt)
                outFile.close()
                print ("finished writing data in file")

                
            except IOError as e:
                mf.updateStat('IOError', 0)
                print ("Error opening file"), e
            except ValueError as e:
                mf.updateStat('ValueError', 0)
                print ("Error writing file"), e
            except:
                mf.updateStat('Error saving', 0)
                print ("Error in saving data")
                outFile.close()

            mf.updateStat('saving done', 0)
            time.sleep(1)
            bp.dataSaved = True
            mf.updateStat('', 1)
            graph()
        dlg.Destroy()

def saveBP(frame,header):
    Zpos = bp.travelZ
    Xcenter = bp.centroid[0] + bp.travelX - (0.5 * bp.Xtravel)
    Ycenter = bp.centroid[1] + bp.travelY - (0.5 * bp.Ytravel)
    Xwidth = bp.secMoment[0]
    Ywidth = bp.secMoment[1]
    writeData = [Zpos, Xcenter,Ycenter,Xwidth,Ywidth]
    filename = 'BP.csv'
    print ("you chose to save BP only...."), Zpos,Xcenter,Ycenter,Xwidth, Ywidth

    if writeData != [0,0,0,0,0]:
        filetypes = "CSV files (*.csv)|*.csv|Text files (*.txt)|*.txt|All files|*"
        dlg = wx.FileDialog(frame,"Choose a directory", defaultFile = filename ,style=wx.FD_SAVE | wx.FD_CHANGE_DIR, wildcard=filetypes)
        if dlg.ShowModal() == wx.ID_OK :
            dirname=dlg.GetDirectory()
            fullPath = os.path.join(dirname, filename)
            print(dirname,"....",filename,"...",fullPath)

            try:
                with open(fullPath) as f:
                    pass
            except IOError:
                # Create text input
                dlg2 = wx.TextEntryDialog(frame, 'Enter some text','Text Entry')
                dlg2.SetValue("")
                if dlg2.ShowModal() == wx.ID_OK:
                    comment = dlg2.GetValue()
                    print('You entered: %s\n' % comment)
                dlg2.Destroy()
                   
                outFile = open(fullPath, "w+")
                outFile.write( header  )
                outFile.write( "\n" )
                outFile.write( comment  )
                outFile.write( "\n" )
                outFile.write( 'Z,X0,Y0,WX,WY'  )
                outFile.write( "\n" )
                outFile.close()
                    
            with open(fullPath,'a') as f:
                print ('opening...',f)
                for n in range(len(writeData)):
                    print ('write data '), n, 'ddd ', writeData[n]
                    f.write(str(writeData[n]))
                    f.write(',')
                f.write('\n')
        dlg.Destroy()
        pass
    
    else:
        print ('no data to save')

    pass



################# Starts Main Here #######################    
app = wx.App()
frame = MyFrame(None, title, xSize, ySize, panelWidth)
frame.Show()
app.MainLoop()




