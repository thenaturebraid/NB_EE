'''
configuration.py adds the parent directory of the
NB repo in sys.path so that modules can be imported
using "from NB_EE..."
'''

import arcpy
import sys
import os

try:
    toolbox = "NB_EE"

    currentPath = os.path.dirname(os.path.abspath(__file__)) # should go to <base path>\NB_EE
    basePath = os.path.dirname(currentPath)

    nbEEPath = os.path.normpath(os.path.join(basePath, "NB_EE"))

    libPath = os.path.join(nbEEPath, "lib")
    displayPath = os.path.join(nbEEPath, "display")
    
    oldScratchPath = os.path.join(nbEEPath, "NBscratch")
    scratchPath = os.path.join(basePath, "NBscratch")

    userSettingsFile = os.path.join(nbEEPath, "user_settings.xml")
    
    # Add basePath to sys.path so that modules can be imported using "import NB_EE.folder.modulename" etc.
    if os.path.normpath(basePath) not in sys.path:
        sys.path.append(os.path.normpath(basePath))

    # Tolerance
    clippingTolerance = 0.00000000001

except Exception:
    arcpy.AddError("Configuration file not read successfully")
    raise
