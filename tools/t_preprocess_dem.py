'''
t_preprocess_dem.py preprocesses the user-provided DEM and stream network to reconcile inconsistencies
between these inputs and produce files that will be used by the other tools in this toolbox
'''

import arcpy
import os
import sys

import NB_EE.lib.log as log
import NB_EE.lib.progress as progress
import NB_EE.lib.common as common
import NB_EE.lib.baseline as baseline
import NB_EE.solo.preprocess_dem as preprocess_dem

from NB_EE.lib.refresh_modules import refresh_modules
from NB_EE.lib.external import six # Python 2/3 compatibility module
refresh_modules([log, common, baseline, preprocess_dem])

def function(params):

    try:
        ###################
        ### Read inputs ###
        ###################

        pText = common.paramsAsText(params)

        outputFolder = pText[1]        
        inputDEM = common.fullPath(pText[2])
        inputStudyAreaMask = pText[3]
        inputStreamNetwork = pText[4]
        streamAccThresh = pText[5]
        riverAccThresh = pText[6]
        smoothDropBuffer = pText[7]
        smoothDrop = pText[8]
        streamDrop = pText[9]
        rerun = common.strToBool(pText[10])

        log.info('Inputs read in')

        ###########################
        ### Tool initialisation ###
        ###########################

        # Create Baseline folder
        if not os.path.exists(outputFolder):
            os.mkdir(outputFolder)

        # Set up logging output to file
        log.setupLogging(outputFolder)

        # Run system checks
        common.runSystemChecks(outputFolder, rerun)

        # Set up progress log file
        progress.initProgress(outputFolder, rerun)

        # Write input params to XML
        common.writeParamsToXML(params, outputFolder, 'PreprocessDEM')

        log.info('Tool initialised')

        ########################
        ### Define filenames ###
        ########################

        studyAreaMask = os.path.join(outputFolder, "studyAreaMask.shp")

        ###############################
        ### Set temporary variables ###
        ###############################

        prefix = os.path.join(arcpy.env.scratchGDB, 'base_')

        DEMTemp = prefix + 'DEMTemp'
        clippedDEM = prefix + 'clippedDEM'
        clippedStreamNetwork = prefix + 'clippedStreamNetwork'

        studyAreaMaskTemp = prefix + "studyAreaMaskTemp"
        studyAreaMaskBuff = prefix + "studyAreaMaskBuff"
        studyAreaMaskDiss = prefix + "studyAreaMaskDiss"

        log.info('Temporary variables set')

        ###################
        ### Data checks ###
        ###################
        
        codeBlock = 'Data checks 1'
        if not progress.codeSuccessfullyRun(codeBlock, outputFolder, rerun):

            # Check DEM has a coordinate system specified
            DEMSpatRef = arcpy.Describe(inputDEM).SpatialReference
            if DEMSpatRef.Name == "Unknown":
                log.error("NB does not permit calculations without the spatial reference for the DEM being defined.") 
                log.error("Please define a projection for your DEM and try again.")
                sys.exit()

            # Reproject DEM if it has a geographic coordinate system
            if DEMSpatRef.type == "Geographic":
                baseline.reprojectGeoDEM(inputDEM, outputDEM=DEMTemp)
                arcpy.CopyRaster_management(DEMTemp, inputDEM)

            # Set environment variables
            arcpy.env.snapRaster = inputDEM

            # Get spatial references of DEM and study area mask
            DEMSpatRef = arcpy.Describe(inputDEM).SpatialReference
            maskSpatRef = arcpy.Describe(inputStudyAreaMask).SpatialReference

            # Reproject study area mask if it does not have the same coordinate system as the DEM
            if not common.equalProjections(DEMSpatRef, maskSpatRef):

                warning = "Study area mask does not have the same coordinate system as the DEM"
                log.warning(warning)
                common.logWarnings(outputFolder, warning)

                warning = "Mask coordinate system is " + maskSpatRef.Name + " while DEM coordinate system is " + DEMSpatRef.Name
                log.warning(warning)
                common.logWarnings(outputFolder, warning)

                warning = "Reprojecting study area mask"
                log.warning(warning)
                common.logWarnings(outputFolder, warning)

                arcpy.Project_management(inputStudyAreaMask, studyAreaMaskTemp, DEMSpatRef)
                arcpy.CopyFeatures_management(studyAreaMaskTemp, studyAreaMask)
            else:
                arcpy.CopyFeatures_management(inputStudyAreaMask, studyAreaMask)

            # If DEM is large, clip it to a large buffer around the study area mask (~5km)
            inputDEM = baseline.clipLargeDEM(inputDEM, studyAreaMask)            

            # Check if input stream network contains data
            baseline.checkInputFC(inputStreamNetwork, outputFolder)

        ###############################
        ### Tidy up study area mask ###
        ###############################

        codeBlock = 'Tidy up study area mask'
        if not progress.codeSuccessfullyRun(codeBlock, outputFolder, rerun):

            # Check how many polygons are in the mask shapefile
            numPolysInMask = int(arcpy.GetCount_management(studyAreaMask).getOutput(0))
            if numPolysInMask > 1:

                # Reduce multiple features where possible
                arcpy.Union_analysis(studyAreaMask, studyAreaMaskDiss, "ONLY_FID", "", "NO_GAPS")
                arcpy.Dissolve_management(studyAreaMaskDiss, studyAreaMask, "", "", "SINGLE_PART", "DISSOLVE_LINES")

            progress.logProgress(codeBlock, outputFolder)

        # Buffer study area mask
        baseline.bufferMask(inputDEM, studyAreaMask, outputStudyAreaMaskBuff=studyAreaMaskBuff)
        log.info('Study area mask buffered')

        #######################
        ### Clip input data ###
        #######################

        codeBlock = 'Clip inputs'
        if not progress.codeSuccessfullyRun(codeBlock, outputFolder, rerun):

            baseline.clipInputs(outputFolder,
                                studyAreaMaskBuff,
                                inputDEM,
                                inputStreamNetwork,
                                outputDEM=clippedDEM,
                                outputStream=clippedStreamNetwork)

            progress.logProgress(codeBlock, outputFolder)

        ###########################
        ### Run HydTopo process ###
        ###########################

        log.info("*** Preprocessing DEM ***")
        preprocess_dem.function(outputFolder,
                                clippedDEM,
                                studyAreaMask,
                                clippedStreamNetwork,
                                streamAccThresh,
                                riverAccThresh,
                                smoothDropBuffer,
                                smoothDrop,
                                streamDrop,
                                rerun)

    except Exception:
        arcpy.SetParameter(0, False)
        log.exception("Preprocessing DEM functions did not complete")
        raise
