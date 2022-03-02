'''
Change user settings tool
'''

import arcpy
import os

import configuration
import NB_EE.lib.common as common

from NB_EE.lib.refresh_modules import refresh_modules
refresh_modules([common])

def function(params):

    common.runSystemChecks() # Run to ensure config.xml is copied across to user_settings.xml if needed. This line can be removed after 31/10/18.

    # Get inputs
    p = common.paramsAsText(params)
    scratchPath = p[1]
    developerMode = common.strToBool(p[2])

    if developerMode == True:
        developerMode = 'Yes'
    else:
        developerMode = 'No'

    # Override the default values from user settings file (if they exist in the file)
    try:
        configValues = [('scratchPath', scratchPath),
                        ('developerMode', developerMode)]

        common.writeXML(configuration.userSettingsFile, configValues)

        arcpy.AddMessage('Scratch path updated: ' + scratchPath)
        arcpy.AddMessage('Developer mode updated: ' + developerMode)

    except Exception:
        raise
