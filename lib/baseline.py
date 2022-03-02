import arcpy
import os
import sys
import numpy as np
import random
import configuration

import NB_EE.lib.log as log
import NB_EE.lib.common as common

from NB_EE.lib.refresh_modules import refresh_modules
refresh_modules([log, common])

def bufferMask(inputDEM, studyAreaMask, outputStudyAreaMaskBuff):

    '''
    Buffer the study area mask by two DEM cells. First check that the DEM covers this new area.
    '''

    # Set temporary variables
    prefix = os.path.join(arcpy.env.scratchGDB, "buffMask_")
    
    studyAreaMaskTemp = prefix + "studyAreaMaskTemp"

    # Get extents (mask has already been reprojected to DEM coord system if necessary)
    maskExtent = arcpy.Describe(studyAreaMask).extent
    DEMExtent = arcpy.Describe(inputDEM).extent

    # Find DEM cellsize
    cellSize = int(float(arcpy.GetRasterProperties_management(inputDEM, "CELLSIZEX").getOutput(0)))    

    # Set buffer distance
    bufferDist = 2 * cellSize

    # Find DEM cell units
    cellSizeUnits = arcpy.Describe(inputDEM).spatialReference.linearUnitName

    # Check DEM extent against mask extent
    if (DEMExtent.XMin > maskExtent.XMin - bufferDist or DEMExtent.XMax < maskExtent.XMax + bufferDist
    or  DEMExtent.YMin > maskExtent.YMin - bufferDist or DEMExtent.YMax < maskExtent.YMax + bufferDist):

        log.error('DEM must be larger than study area mask')
        log.error('It must extend beyond study area mask by ' + str(bufferDist) + ' ' + str(cellSizeUnits) + 's')
        sys.exit()

    # Dissolve mask
    arcpy.Dissolve_management(studyAreaMask, studyAreaMaskTemp)

    # Buffer mask so that streams extend beyond the study area boundary
    arcpy.Buffer_analysis(studyAreaMaskTemp, outputStudyAreaMaskBuff, str(bufferDist) + ' ' + str(cellSizeUnits))


def clipLargeDEM(DEM, StudyAreaMask):

    try:
        # Work out filesize of DEM
        cols = arcpy.GetRasterProperties_management(DEM, "COLUMNCOUNT").getOutput(0)
        rows = arcpy.GetRasterProperties_management(DEM, "ROWCOUNT").getOutput(0)
        bitType = int(arcpy.GetRasterProperties_management(DEM, "VALUETYPE").getOutput(0))

        if bitType <= 4:    # 8 bit
            bytes = 1
        elif bitType <= 6:  # 16 bit
            bytes = 2
        elif bitType <= 9:  # 32 bit
            bytes = 4
        elif bitType <= 14: # 64 bit
            bytes = 8
        else:
            bytes = 4

        sizeInGb = int(cols) * int(rows) * bytes / (1024 * 1024 * 1024)

        if sizeInGb > 1: # 1Gb
            log.info('Clipping DEM as original DEM is too large (approximately ' + str(sizeInGb) + 'Gb)')

            # Buffer study area mask by 5km            
            bufferSAM = os.path.join(arcpy.env.scratchGDB, "bufferSAM")
            arcpy.Buffer_analysis(StudyAreaMask, bufferSAM, "5000 meters", "FULL", "ROUND", "ALL")

            # Clip DEM to this buffered area
            bufferedDEM = os.path.join(arcpy.env.scratchWorkspace, "bufferedDEM")
            extent = arcpy.Describe(bufferSAM).extent
            arcpy.Clip_management(DEM, str(extent), bufferedDEM, bufferSAM, nodata_value="-3.402823e+038", clipping_geometry="ClippingGeometry", maintain_clipping_extent="NO_MAINTAIN_EXTENT")

            return bufferedDEM
        else:
            return DEM

    except Exception:
        log.error("Error occurred when determining if DEM needs to be clipped or not")
        raise

def checkInputFC(featureClass, baseFolder):

    # Find number of rows in feature class. arcpy.GetCount_management(featureClass).getOutput(0) should work but doesn't in some cases. KM
    rows = [row for row in arcpy.da.SearchCursor(featureClass, "*")]
    numFeatures = len(rows)
    if numFeatures == 0:
        warning = 'Input feature class ' + featureClass + ' contains no data. Please check file'
        log.warning(warning)
        common.logWarnings(baseFolder, warning)

def reprojectGeoDEM(inputDEM, outputDEM):

    from NB_EE.lib.external import utm

    log.info("DEM has geographic coordinate system. Reprojecting...")

    DEMSpatRef = arcpy.Describe(inputDEM).SpatialReference
    DEMExtent = arcpy.Describe(inputDEM).extent

    # Find midpoint of raster
    midPointX = DEMExtent.XMin + (DEMExtent.XMax - DEMExtent.XMin) / 2
    midPointY = DEMExtent.YMin + (DEMExtent.YMax - DEMExtent.YMin) / 2

    # Find out which UTM zone the DEM should be projected to
    northing, easting, zone, letter = utm.from_latlon(midPointY, midPointX)
    if letter >= "N":
        northSouth = "N"
    else:
        northSouth = "S"

    # Create the new projected coordinate system
    projSpatRef = arcpy.SpatialReference("WGS 1984 UTM Zone " + str(zone) + northSouth)

    # Obtain the transformation string to transform from GCS to PCS
    transformation = arcpy.ListTransformations(DEMSpatRef, projSpatRef, DEMExtent)[0]

    # Reproject DEM to Projected Coord System
    arcpy.ProjectRaster_management(inputDEMRaster, outputDEM, projSpatRef, geographic_transform=transformation)

    # Update coord system
    DEMSpatRef = arcpy.Describe(outputDEM).SpatialReference
    log.info("DEM coordinate system is now " + DEMSpatRef.Name)


def clipInputs(baseFolder, contribAreaBuffered, inputDEM, inputStreamNetwork, outputDEM, outputStream):

    try:
        log.info("Clipping input data")

        # Set temporary variables
        prefix = os.path.join(arcpy.env.scratchGDB, "clip_")

        DEMCopy = prefix + "DEMCopy"
        resampledRain = prefix + "resampledRain"
        resampledRainTemp = prefix + "resampledRainTemp"
        resampledAE = prefix + "resampledAE"
        resampledAETemp = prefix + "resampledAETemp"
        rainTemp = prefix + "rainTemp"
        evapTemp = prefix + "evapTemp"

        # Clip DEM
        # Check DEM not compressed. If it is, uncompress before clipping.
        compression = arcpy.Describe(inputDEM).compressionType
        if compression.lower != 'none':
            arcpy.env.compression = "None"
            arcpy.CopyRaster_management(inputDEM, DEMCopy)
            arcpy.Clip_management(DEMCopy, "#", outputDEM, contribAreaBuffered, clipping_geometry="ClippingGeometry")
        else:
            arcpy.Clip_management(inputDEM, "#", outputDEM, contribAreaBuffered, clipping_geometry="ClippingGeometry")

        DEMSpatRef = arcpy.Describe(outputDEM).SpatialReference

        # Set environment variables
        arcpy.env.snapRaster = outputDEM
        arcpy.env.extent = outputDEM
        arcpy.env.cellSize = outputDEM

        # Clip steam network
        if inputStreamNetwork == None:
            outputStream = None
        else:
            arcpy.Clip_analysis(inputStreamNetwork, contribAreaBuffered, outputStream, configuration.clippingTolerance)

        log.info("Input data clipped successfully")

    except Exception:
        log.error("Input data clipping did not complete successfully")
        raise
