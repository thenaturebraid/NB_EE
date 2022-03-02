import arcpy
import os
import numpy as np
from scipy.ndimage.morphology import binary_dilation

import NB_EE.lib.common as common
import NB_EE.lib.log as log

from NB_EE.lib.refresh_modules import refresh_modules
refresh_modules([log, common])

def function(params):

    try:
        # Get inputs
        pText = common.paramsAsText(params)
        outputRaster = pText[1]
        studyAreaMask = pText[2]
        fdr = pText[3]

        common.runSystemChecks()

        # Snap rasters to flow direction raster grid
        arcpy.env.snapRaster = fdr

        # Set temporary filenames
        prefix = "terrflow_"
        baseTempName = os.path.join(arcpy.env.scratchGDB, prefix)

        fdrClip = baseTempName + "fdrClip"
        studyAreaDissolved = baseTempName + "studyAreaDissolved"
        studyAreaRaster = baseTempName + "studyAreaRaster"
        studyAreaBinary = baseTempName + "studyAreaBinary"
        studyAreaBoundary = baseTempName + "studyAreaBoundary"
        studyAreaBoundaryRaster = baseTempName + "studyAreaBoundaryRaster"
        studyAreaBoundaryBinary = baseTempName + "studyAreaBoundaryBinary"

        ######################################
        ### Flow direction raster to numpy ###
        ######################################

        # Clip flow direction raster to study area
        arcpy.sa.ExtractByMask(fdr, studyAreaMask).save(fdrClip)

        # Convert flow direction raster to numpy array
        fdrArray = arcpy.RasterToNumPyArray(fdrClip)
        fdrArray.astype(int)
        rows, cols = fdrArray.shape # Returns the rows, columns

        log.info('Flow direction raster converted to numpy array')

        ###########################
        ### Study area to numpy ###
        ###########################

        # Dissolve the study area mask
        arcpy.Dissolve_management(studyAreaMask, studyAreaDissolved)

        log.info('Study area mask dissolved')

        # Convert the dissolved study area to a raster
        cellsize = float(arcpy.GetRasterProperties_management(fdr, "CELLSIZEX").getOutput(0))
        arcpy.FeatureToRaster_conversion(studyAreaDissolved, "Shape_Length", studyAreaRaster, cell_size=cellsize)

        log.info('Study area mask converted to raster')

        # Convert study area to raster with value of 1
        tempRas = arcpy.sa.Con(studyAreaRaster, 1)
        tempRas.save(studyAreaBinary)

        # Convert raster to numpy array
        studyAreaArray = arcpy.RasterToNumPyArray(studyAreaBinary)
        studyAreaArray.astype(int)

        log.info('Study area raster converted to numpy array')

        ##############################################
        ### Create study area boundary numpy array ###
        ##############################################

        # Pad the study area array with zeros around the edges (creating an array one cell larger in each direction)
        x_offset = 1
        y_offset = 1
        zeroPaddedStudyAreaArray = np.zeros(shape=(rows + 2, cols + 2), dtype=int)
        zeroPaddedStudyAreaArray[x_offset:studyAreaArray.shape[0]+x_offset,y_offset:studyAreaArray.shape[1]+y_offset] = studyAreaArray

        # Find the cells on the boundary of the study area
        k = np.ones((3,3),dtype=int) # for 4-connected
        zeroPaddedstudyAreaBoundaryArray = binary_dilation(zeroPaddedStudyAreaArray==0, k) & zeroPaddedStudyAreaArray

        # Remove the zero padding
        studyAreaBoundaryArray = zeroPaddedstudyAreaBoundaryArray[1:-1, 1:-1]

        #################################
        ### Set up output numpy array ###
        #################################

        outArray = np.zeros(shape=(rows, cols), dtype=int)

        # Loop through the rows
        for rowNum in xrange(rows):

            # Loop through the row's columns
            for colNum in xrange(cols):

                # Get the value from the study area boundary cell
                boundaryValue = studyAreaBoundaryArray.item(rowNum, colNum)

                if boundaryValue != 0:

                    # Get the value from the flow direction cell
                    fdrValue = fdrArray.item(rowNum, colNum)

                    '''
                    arcpy.AddMessage('=============')
                    arcpy.AddMessage('rowNum: ' + str(rowNum))
                    arcpy.AddMessage('colNum: ' + str(colNum))
                    arcpy.AddMessage('fdrValue: ' + str(fdrValue))
                    '''

                    # Direction east
                    if fdrValue == 1:
                        endX = 1
                        endY = 0

                    # Direction south east
                    elif fdrValue == 2:
                        endX = 1
                        endY = 1

                    # Direction south
                    elif fdrValue == 4:
                        endX = 0
                        endY = 1

                    # Direction south west
                    elif fdrValue == 8:
                        endX = -1
                        endY = 1

                    # Direction west
                    elif fdrValue == 16:
                        endX = -1
                        endY = 0

                    # Direction north west
                    elif fdrValue == 32:
                        endX = -1
                        endY = -1

                    # Direction north
                    elif fdrValue == 64:
                        endX = 0
                        endY = -1

                    # Direction north east
                    elif fdrValue == 128:
                        endX = 1
                        endY = -1

                    # Start X and Y are on the other side of the central cell
                    startX = endX * -1
                    startY = endY * -1

                    # Work out start and end rows and columns
                    startRow = rowNum + startY
                    startCol = colNum + startX
                    endRow = rowNum + endY
                    endCol = colNum + endX

                    '''
                    arcpy.AddMessage('startRow: ' + str(startRow))
                    arcpy.AddMessage('startCol: ' + str(startCol))
                    arcpy.AddMessage('endRow: ' + str(endRow))
                    arcpy.AddMessage('endCol: ' + str(endCol))
                    '''

                    # Set start value
                    if (startRow < 0 or startRow >= rows
                     or startCol < 0 or startCol >= cols):
                        startValue = 0
                    else:
                        startValue = studyAreaArray.item(startRow, startCol)

                    # Set end value
                    if (endRow < 0 or endRow >= rows
                     or endCol < 0 or endCol >= cols):
                        endValue = 0
                    else:
                        endValue = studyAreaArray.item(endRow, endCol)

                    '''
                    arcpy.AddMessage('startValue: ' + str(startValue))
                    arcpy.AddMessage('endValue: ' + str(endValue))
                    '''

                    # Water flows out of study area
                    if startValue == 1 and endValue == 0:
                        outValue = 1

                    # Water flows into study area
                    if startValue == 0 and endValue == 1:
                        outValue = 2

                    # Water flows along study area boundary (ridgeline)
                    if ((startValue == 0 and endValue == 0)
                     or (startValue == 1 and endValue == 1)):
                        outValue = 3

                    # Set the output array value
                    outArray.itemset((rowNum, colNum), outValue)

        # Convert numpy array back to a raster
        dsc = arcpy.Describe(fdrClip)
        sr = dsc.SpatialReference
        ext = dsc.Extent
        lowerLeftCorner = arcpy.Point(ext.XMin, ext.YMin)

        outRasterTemp = arcpy.NumPyArrayToRaster(outArray, lowerLeftCorner, dsc.meanCellWidth, dsc.meanCellHeight)
        arcpy.DefineProjection_management(outRasterTemp, sr)

        # Set zero values in raster to NODATA
        outRasterTemp2 = arcpy.sa.SetNull(outRasterTemp, outRasterTemp, "VALUE = 0")

        # Save raster
        outRasterTemp2.save(outputRaster)

        log.info('Terrestrial flow raster created')

        # Save flow direction raster in degrees (for display purposes)
        degreeValues = arcpy.sa.RemapValue([[1, 90], [2, 135], [4, 180], [8, 225], [16, 270], [32, 315], [64, 0], [128, 45]])
        fdrDegrees = os.path.join(os.path.dirname(outputRaster), "fdr_degrees")
        arcpy.sa.Reclassify(fdr, "Value", degreeValues, "NODATA").save(fdrDegrees)
        arcpy.SetParameter(4, fdrDegrees)

        # Set output success parameter - the parameter number is zero based (unlike the input parameters)
        arcpy.SetParameter(0, True)

    except Exception:
        arcpy.SetParameter(0, False)
        arcpy.AddMessage('Terrestrial flow direction operations did not complete successfully')
        raise
