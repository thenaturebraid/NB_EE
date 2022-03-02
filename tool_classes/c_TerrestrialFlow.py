import arcpy
import os
import configuration
from NB_EE.lib.refresh_modules import refresh_modules

class TerrestrialFlow(object):

    class ToolValidator:
        """Class for validating a tool's parameter values and controlling the behavior of the tool's dialog."""
    
        def __init__(self, parameters):
            """Setup the Geoprocessor and the list of tool parameters."""
            self.params = parameters
    
        def initializeParameters(self):
            """Refine the properties of a tool's parameters.
            This method is called when the tool is opened."""
            return
        
        def updateParameters(self):
            """Modify the values and properties of parameters before internal validation is performed.
            This method is called whenever a parameter has been changed."""
            return
    
        def updateMessages(self):
            """Modify the messages created by internal validation for each tool parameter.
            This method is called after internal validation."""

            import NB_EE.lib.input_validation as input_validation
            refresh_modules(input_validation)
            
            input_validation.checkFilePaths(self)
    
    def __init__(self):
        self.label = u'03 Show terrestrial flow'
        self.description = u''
        self.canRunInBackground = False

    def getParameterInfo(self):

        params = []

        # 0 Output__Success
        param = arcpy.Parameter()
        param.name = u'Output__Success'
        param.displayName = u'Output: Success'
        param.parameterType = 'Derived'
        param.direction = 'Output'
        param.datatype = u'Boolean'
        params.append(param)

        # 1 Output_raster
        param = arcpy.Parameter()
        param.name = u'Output_raster'
        param.displayName = u'Output raster'
        param.parameterType = 'Required'
        param.direction = 'Output'
        param.datatype = u'Raster Dataset'
        param.symbology = os.path.join(configuration.displayPath, "terrflow.lyr")
        params.append(param)

        # 2 Study area mask
        param = arcpy.Parameter()
        param.name = u'Study_area_mask'
        param.displayName = u'Study area mask'
        param.parameterType = 'Required'
        param.direction = 'Input'
        param.datatype = u'Feature Class'
        params.append(param)

        # 3 Flow direction raster
        param = arcpy.Parameter()
        param.name = u'Flow_direction_raster'
        param.displayName = u'Flow direction raster'
        param.parameterType = 'Required'
        param.direction = 'Input'
        param.datatype = u'Raster Dataset'
        params.append(param)

        # 4 Flow direction raster in degrees
        param = arcpy.Parameter()
        param.name = u'Flow_direction_degrees'
        param.displayName = u'Flow direction raster in degrees'
        param.parameterType = 'Derived'
        param.direction = 'Output'
        param.datatype = u'Raster Dataset'
        param.symbology = os.path.join(configuration.displayPath, "hydfdrdeg.lyr")
        params.append(param)

        return params

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        validator = getattr(self, 'ToolValidator', None)
        if validator:
             return validator(parameters).updateParameters()

    def updateMessages(self, parameters):
        validator = getattr(self, 'ToolValidator', None)
        if validator:
             return validator(parameters).updateMessages()

    def execute(self, parameters, messages):

        import NB_EE.tools.t_terrestrial_flow as t_terrestrial_flow
        refresh_modules(t_terrestrial_flow)

        t_terrestrial_flow.function(parameters)
