#! Python 3

import math
import BeamProfiler as bp

v = 3.4

#This file defines the fuctions to process data
#crated F. Durville 3 Feb 2020
#last update - FD-26oct20

#calculating default bkg value
def CalcBkg(scan,imgData):
    bkg = 0
    sumX = 0
    sumY = 0

    if scan == "2D":
        pass
    
    elif scan == "X" or scan == "Y" or scan == "XY":
        np = len(imgData)
        for nn in range(2):
            sumX = sumX + imgData[nn][1]
            sumY = sumY + imgData[nn][1]
        for nn in range(np-2,np):
            try:
                sumX = sumX + imgData[nn][1]
                sumY = sumY + imgData[nn][1]
            except IndexError:
                print ("CalcBkg index error - ignored.."),nn
                pass

    else: 
        print ("Error in CalcBkg....")
        pass
            
    bkg = sumX + sumY
    bkg = bkg / 8
    return bkg


#calculating centroid
def calc_centroid(imgData):
    Xcentroid = 0
    Ycentroid = 0
    centr = 0
    sumI = 0
    sumIx = 0
    sumIy = 0
    centroid = [0,0]
    step = bp.stepXY
    scan = bp.scan
    np = len(imgData)

    if scan == "X" or scan == "Y":
        for nn in range(np):
            travel = step * nn
            sumI = sumI + imgData[nn][1]
            centr = centr + travel*imgData[nn][1]
        if scan == "X":
            centroid[0] = centr / sumI
        if scan == "Y":
            centroid[1] = centr / sumI
        pass

    if scan == "XY":
        for nn in range(1,np):
            travel = step * nn
            sumIx = sumIx + imgData[nn][0]
            Xcentroid = Xcentroid + travel*imgData[nn][0]
            try:
                sumIy = sumIy + imgData[nn][1]
                Ycentroid = Ycentroid + travel*imgData[nn][1]
            except IndexError:
                print ("centroid index error - ignored.."),nn
                pass
        centroid[0] = Xcentroid / sumIx
        centroid[1] = Ycentroid / sumIy
        
    if scan == '2D':  # not finished - FD-30oct20
        npx = len(imgData[0])
        print ("length: "),np," npx ",npx
        
        for nn in range(np):
            travel = step * nn
            sumIx = sumIx + imgData[nn][0]
            Xcentroid = Xcentroid + travel*imgData[nn][0]
            try:
                sumIy = sumIy + imgData[nn][1]
                Ycentroid = Ycentroid + travel*imgData[nn][1]
            except IndexError:
                print ("centroid index error - ignored.."),nn
                pass
            
        centroid[0] = Xcentroid / sumIx
        centroid[1] = Ycentroid / sumIy
        pass
        
    bp.centroid = centroid
        
    return centroid

#calculating Second Moment
def calc_secmom(imgData):
    if bp.centroid[0]==0 or bp.centroid[1]==0:
        bp.centroid = calc_centroid(imgData)
        pass
    Xmom = 0
    Ymom = 0
    sumIx = 0
    sumIy = 0
    Xc = bp.centroid[0]
    Yc = bp.centroid[1]
    secMoment = [0,0]
    step = bp.stepXY
    scan = bp.scan
    np = len(imgData)
    
    if scan == "X" or scan == "Y":
        for nn in range(np):
            travel = step * nn
            if scan == "X":
                 sumIx = sumIx + imgData[nn][1]
                 Xmom = Xmom + (((travel - Xc)*(travel - Xc))*imgData[nn][1])
            if scan == "Y":
                 sumIy = sumIy + imgData[nn][1]
                 Ymom = Ymom + (((travel - Yc)*(travel - Yc))*imgData[nn][1])

        if scan == "X":     
            secMoment[0] = math.sqrt((Xmom / sumIx))
            secMoment[0] = secMoment[0] * 4
        if scan == "Y":
            secMoment[1] = math.sqrt((Ymom / sumIy))
            secMoment[1] = secMoment[1] * 4
        pass

    if scan == "XY" or scan == "XYZ":  #added FD-30oct20
        print ("length: "),np,"imgData"
        print imgData
        for nn in range(np):
            travel = step * nn
            sumIx = sumIx + imgData[nn][0]
            Xmom = Xmom + (((travel - Xc)*(travel - Xc))*imgData[nn][0])
            try:
                sumIy = sumIy + imgData[nn][1]
                Ymom = Ymom + (((travel - Yc)*(travel - Yc))*imgData[nn][1])
            except IndexError:
                print ("secmom index error - ignored.."),nn
                pass
        print ("secmom sumIx sumIy Xmom Ymom..."),nn
        print sumIx,"...",sumIy,"...",Xmom,"...",Ymom
        secMoment[0] = math.sqrt((Xmom / sumIx))
        secMoment[1] = math.sqrt((Ymom / sumIy))
        secMoment[0] = secMoment[0] * 4
        secMoment[1] = secMoment[1] * 4
        
    if scan == '2D':        # not finished  -  FD-30oct20
        npx = len(imgData[0])
        print ("length: "),np," npx ",npx
        
        pass
    
    print ("secMomX:"),secMoment[0],"secMomY:",secMoment[1]
    return secMoment

#reconstructing data to be plotted
def rebuildData(imgData, step):
    data = []
    np = len(imgData)
    for n in range(np):
        travel = step * n
        try:
            datVal = imgData[n][1]
            travel = step * n
            dataPoint = (travel,datVal)
            data.append(dataPoint)
        except IndexError:
            print ("rebuild index error - ignored.."),n
            pass
    return data

#subtracting background value
def subtractBkg(scan,imgData, bkg):
    np = len(imgData)
    nr = len(imgData[0])
    if scan == "X" or scan == "Y":
        #np = len(imgData)
        for nn in range(np):
            imgData[nn] = (imgData[nn][0],imgData[nn][1] - bkg)
            if imgData[nn][1] < 0:
                imgData[nn] = (imgData[nn][0],0)
    elif scan == "XY":        
        #np = len(imgData)
        print ("imgData length: ", np)
        for nn in range(np):
            #print "imgData value : ", imgData[nn]
            try:
                if  (imgData[nn][0] - bkg) >= 0 and  (imgData[nn][1] - bkg) >= 0:             
                    imgData[nn] = (imgData[nn][0] - bkg, imgData[nn][1] - bkg)
                elif (imgData[nn][0] - bkg) >= 0 and  (imgData[nn][1] - bkg) < 0:
                    imgData[nn] = (imgData[nn][0] - bkg, 0)
                elif (imgData[nn][0] - bkg) < 0 and  (imgData[nn][1] - bkg) >= 0:
                    imgData[nn] = (0, imgData[nn][1] - bkg)
                elif (imgData[nn][0] - bkg) < 0 and  (imgData[nn][1] - bkg) < 0: #added FD-26oct20
                    imgData[nn] = (0, 0)
            except IndexError:
                print ("subBkg index error - ignored..")
                try:
                    imgData[nn] = (imgData[nn][0],0)  #added V3-19sep20
                    if  (imgData[nn][0] - bkg) >= 0:
                        imgData[nn] = (imgData[nn][0] - bkg,0)
                    else:
                        imgData[nn] = (0,0)
                except:
                    print ("subBkg error....."),nn,"  ",imData[nn]
                pass
            
    elif scan == "2D":
        for nn in range(np):
            for nnn in range(nr):
                try:
                    if  (imgData[nn][nr] - bkg) >= 0 :             
                        imgData[nn] = (imgData[nn][0] - bkg, imgData[nn][1] - bkg)
                    else:
                        imgData[nn] = (0, 0)
                except:
                    pass

    #print "Done sub bkg..."
    bp.resetProcess()
    return imgData

 
