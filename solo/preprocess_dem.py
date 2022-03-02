'''
Preprocessing tool for NB_EE. Generates hydrological and topographical files
for use in other NB_EE functions.
'''
import arcpy
from arcpy.sa import Int, Reclassify, RemapRange, RemapValue, Raster, Fill, Float
from arcpy.sa import FlowAccumulation, FlowDirection, StreamOrder
import os

import NB_EE.lib.progress as progress
import NB_EE.lib.log as log
import NB_EE.lib.common as common
import NB_EE.solo.reconditionDEM as reconditionDEM
import NB_EE.lib.baseline as baseline

from NB_EE.lib.refresh_modules import refresh_modules
refresh_modules([log, common, reconditionDEM, baseline])


def function(outputFolder, DEM, studyAreaMask, streamInput, minAccThresh, majAccThresh,
             smoothDropBuffer, smoothDrop, streamDrop, rerun=False):

    try:
        # Set environment variables
        arcpy.env.compression = "None"
        arcpy.env.snapRaster = DEM
        arcpy.env.extent = DEM
        arcpy.env.cellSize = arcpy.Describe(DEM).meanCellWidth

        ########################
        ### Define filenames ###
        ########################

        rawDEM = os.path.join(outputFolder, "rawDEM")
        hydDEM = os.path.join(outputFolder, "hydDEM")
        hydFDR = os.path.join(outputFolder, "hydFDR")
        hydFDRDegrees = os.path.join(outputFolder, "hydFDRDegrees")
        hydFAC = os.path.join(outputFolder, "hydFAC")
        streamInvRas = os.path.join(outputFolder, "streamInvRas") # Inverse stream raster - 0 for stream, 1 for no stream
        streams = os.path.join(outputFolder, "streams.shp")
        streamDisplay = os.path.join(outputFolder, "streamDisplay.shp")
        multRaster = os.path.join(outputFolder, "multRaster")
        hydFACInt = os.path.join(outputFolder, "hydFACInt")

        ###############################
        ### Set temporary variables ###
        ###############################

        prefix = os.path.join(arcpy.env.scratchGDB, "base_")

        cellSizeDEM = float(arcpy.env.cellSize)

        burnedDEM = prefix + "burnedDEM"
        streamAccHaFile = prefix + "streamAccHa"
        rawFDR = prefix + "rawFDR"        
        allPolygonSinks = prefix + "allPolygonSinks"
        DEMTemp = prefix + "DEMTemp"
        hydFACTemp = prefix + "hydFACTemp"

        # Saved as .tif as did not save as ESRI grid on server
        streamsRasterFile = os.path.join(arcpy.env.scratchFolder, "base_") + "StreamsRaster.tif"

        ###############################
        ### Save DEM to base folder ###
        ###############################

        codeBlock = 'Save DEM'
        if not progress.codeSuccessfullyRun(codeBlock, outputFolder, rerun):

            # Save DEM to base folder as raw DEM with no compression
            pixelType = int(arcpy.GetRasterProperties_management(DEM, "VALUETYPE").getOutput(0))

            if pixelType == 9: # 32 bit float
                arcpy.CopyRaster_management(DEM, rawDEM, pixel_type="32_BIT_FLOAT")
            else:
                log.info("Converting DEM to 32 bit floating type")
                arcpy.CopyRaster_management(DEM, DEMTemp)
                arcpy.CopyRaster_management(Float(DEMTemp), rawDEM, pixel_type="32_BIT_FLOAT")

            # Calculate statistics for raw DEM
            arcpy.CalculateStatistics_management(rawDEM)

            progress.logProgress(codeBlock, outputFolder)

        ################################
        ### Create multiplier raster ###
        ################################

        codeBlock = 'Create multiplier raster'
        if not progress.codeSuccessfullyRun(codeBlock, outputFolder, rerun):

            Reclassify(rawDEM, "Value", RemapRange([[-999999.9, 999999.9, 1]]), "NODATA").save(multRaster)
            progress.logProgress(codeBlock, outputFolder)


        #######################
        ### Burn in streams ###
        #######################

        codeBlock = 'Burn in streams'
        if not progress.codeSuccessfullyRun(codeBlock, outputFolder, rerun):

            # Recondition DEM (burning stream network in using AGREE method)
            log.info("Burning streams into DEM.")
            reconditionDEM.function(rawDEM, streamInput, smoothDropBuffer, smoothDrop, streamDrop, burnedDEM)
            log.info("Completed stream network burn in to DEM")

            progress.logProgress(codeBlock, outputFolder)

        ##################
        ### Fill sinks ###
        ##################

        codeBlock = 'Fill sinks'
        if not progress.codeSuccessfullyRun(codeBlock, outputFolder, rerun):

            Fill(burnedDEM).save(hydDEM)

            log.info("Sinks in DEM filled")
            progress.logProgress(codeBlock, outputFolder)

        ######################
        ### Flow direction ###
        ######################

        codeBlock = 'Flow direction'
        if not progress.codeSuccessfullyRun(codeBlock, outputFolder, rerun):

            FlowDirection(hydDEM, "NORMAL").save(hydFDR)
            log.info("Flow Direction calculated")
            progress.logProgress(codeBlock, outputFolder)

        #################################
        ### Flow direction in degrees ###
        #################################

        codeBlock = 'Flow direction in degrees'
        if not progress.codeSuccessfullyRun(codeBlock, outputFolder, rerun):

            # Save flow direction raster in degrees (for display purposes)
            degreeValues = RemapValue([[1, 90], [2, 135], [4, 180], [8, 225], [16, 270], [32, 315], [64, 0], [128, 45]])
            Reclassify(hydFDR, "Value", degreeValues, "NODATA").save(hydFDRDegrees)
            progress.logProgress(codeBlock, outputFolder)

        #########################
        ### Flow accumulation ###
        #########################

        codeBlock = 'Flow accumulation'
        if not progress.codeSuccessfullyRun(codeBlock, outputFolder, rerun):

            hydFACTemp = FlowAccumulation(hydFDR, "", "FLOAT")
            hydFACTemp.save(hydFAC)
            arcpy.sa.Int(Raster(hydFAC)).save(hydFACInt) # integer version
            log.info("Flow Accumulation calculated")

            progress.logProgress(codeBlock, outputFolder)


        ##########################
        ### Create stream file ###
        ##########################

        codeBlock = 'Create stream file'
        if not progress.codeSuccessfullyRun(codeBlock, outputFolder, rerun):
            
            # Create accumulation in metres
            streamAccHaFile = hydFACTemp * cellSizeDEM * cellSizeDEM / 10000.0

            # Check stream initiation threshold reached
            streamYes = float(arcpy.GetRasterProperties_management(streamAccHaFile, "MAXIMUM").getOutput(0))

            if streamYes > float(minAccThresh):

                reclassifyRanges = RemapRange([[-1000000, float(minAccThresh), 1],
                                               [float(minAccThresh), 9999999999, 0]])

                outNBstream = Reclassify(streamAccHaFile, "VALUE", reclassifyRanges)
                outNBstream.save(streamInvRas)
                del outNBstream
                log.info("Stream raster for input to NB created")

                # Create stream file for display
                reclassifyRanges = RemapRange([[0, float(minAccThresh), "NODATA"],
                                    [float(minAccThresh), float(majAccThresh), 1],
                                    [float(majAccThresh), 99999999999999, 2]])

                streamsRaster = Reclassify(streamAccHaFile, "Value", reclassifyRanges, "NODATA")
                streamOrderRaster = StreamOrder(streamsRaster, hydFDR, "STRAHLER")
                streamsRaster.save(streamsRasterFile)

                # Create two streams feature classes - one for analysis and one for display
                arcpy.sa.StreamToFeature(streamOrderRaster, hydFDR, streams, 'NO_SIMPLIFY')
                arcpy.sa.StreamToFeature(streamOrderRaster, hydFDR, streamDisplay, 'SIMPLIFY')

                # Rename grid_code column to 'Strahler'
                for streamFC in [streams, streamDisplay]:

                    arcpy.AddField_management(streamFC, "Strahler", "LONG")
                    arcpy.CalculateField_management(streamFC, "Strahler", "!GRID_CODE!", "PYTHON_9.3")
                    arcpy.DeleteField_management(streamFC, "GRID_CODE")

                del streamsRaster
                del streamOrderRaster

                log.info("Stream files created")

            else:

                warning = 'No streams initiated'
                log.warning(warning)
                common.logWarnings(outputFolder, warning)

                # Create NBStream file from multiplier raster (i.e. all cells have value of 1 = no stream)
                arcpy.CopyRaster_management(multRaster, streamInvRas)

            progress.logProgress(codeBlock, outputFolder)

        codeBlock = 'Clip data, build pyramids and generate statistics'
        if not progress.codeSuccessfullyRun(codeBlock, outputFolder, rerun):

            try:
                # Generate pyramids and stats
                arcpy.BuildPyramidsandStatistics_management(outputFolder, "", "", "", "")
                log.info("Pyramids and Statistics calculated for all NB topographical information rasters")

            except Exception:
                log.info("Warning - could not generate all raster statistics")

            progress.logProgress(codeBlock, outputFolder)

        # Reset snap raster
        arcpy.env.snapRaster = None
        
    except Exception:
        log.error("Error in preprocessing operations")
        raise
