# -*- coding: utf-8 -*-
import arcpy
import os
import sys

import configuration
try:
    reload(configuration)  # Python 2.7
except NameError:
    try:
        import importlib # Python 3.4
        importlib.reload(configuration)
    except Exception:
    	arcpy.AddError('Could not load configuration module')
    	sys.exit()

# Load and refresh the refresh_modules module
from NB_EE.lib.external.six.moves import reload_module
import NB_EE.lib.refresh_modules as refresh_modules
reload_module(refresh_modules)
from NB_EE.lib.refresh_modules import refresh_modules

import NB_EE.lib.input_validation as input_validation
refresh_modules(input_validation)

#############
### Tools ###
#############

import NB_EE.tool_classes.c_InitialiseToolbox as c_InitialiseToolbox
refresh_modules(c_InitialiseToolbox)
InitialiseToolbox = c_InitialiseToolbox.InitialiseToolbox

import NB_EE.tool_classes.c_TerrestrialFlow as c_TerrestrialFlow
refresh_modules(c_TerrestrialFlow)
TerrestrialFlow = c_TerrestrialFlow.TerrestrialFlow

import NB_EE.tool_classes.c_EntryExits as c_EntryExits
refresh_modules(c_EntryExits)
StreamEntryExits = c_EntryExits.StreamEntryExits

import NB_EE.tool_classes.c_PreprocessDEM as c_PreprocessDEM
refresh_modules(c_PreprocessDEM)
PreprocessDEM = c_PreprocessDEM.PreprocessDEM

##########################
### Toolbox definition ###
##########################

class Toolbox(object):

    def __init__(self):
        self.label = u'Nature Braid Entry Exits tool'
        self.alias = u'NB'
        self.tools = [InitialiseToolbox, TerrestrialFlow, StreamEntryExits, PreprocessDEM]
        