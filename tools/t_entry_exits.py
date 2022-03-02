import arcpy
import os

import NB_EE.lib.log as log
import NB_EE.lib.common as common
import NB_EE.solo.entry_exits as entry_exits

from NB_EE.lib.refresh_modules import refresh_modules
refresh_modules([log, common, entry_exits])

def function(params):

    try:
        pText = common.paramsAsText(params)

        # Get inputs
        outputFolder = pText[1]
        studyMask = pText[3]
        streamNetwork = pText[4]
        facRaster = pText[5]
        fdrRaster = pText[6]

        # Run system checks
        common.runSystemChecks()

        # Set up logging output to file
        log.setupLogging(outputFolder)

        # Call Entry Exits function
        entryExitPoints, streamNetworkFC, watershedsFC = entry_exits.function(outputFolder, studyMask, streamNetwork, facRaster, fdrRaster)
        
        # Set outputs
        if entryExitPoints is not None:
            arcpy.SetParameter(2, entryExitPoints)

        arcpy.SetParameter(7, streamNetworkFC)
        arcpy.SetParameter(8, studyMask)
        arcpy.SetParameter(9, watershedsFC)

        arcpy.SetParameter(0, True)
        log.info("Entry/exits operations completed successfully")

    except Exception:
        log.exception("Entry/exits tool failed")
        raise
