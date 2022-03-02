import os

from NB_EE.lib.external import six # Python 2/3 compatibility module

def checkFilePaths(self):

    for i in range(0, len(self.params)):
        if self.params[i].datatype in ["Folder", "Feature Layer", "Feature Class", "Raster Layer", "Raster Dataset", "File"]:

            # Check for spaces
            if " " in str(self.params[i].valueAsText) and not self.params[i].name.lower().endswith("overseer_xml_file"):
                self.params[i].setErrorMessage("Value: " + str(self.params[i].valueAsText) + ". The file path contains spaces. Please choose a file path without spaces")

            # Check for files being in OneDrive or Dropbox folders
            if "OneDrive" in str(self.params[i].valueAsText):
                self.params[i].setErrorMessage("Value: " + str(self.params[i].valueAsText) + ". The file/folder is located inside a OneDrive folder. Please move the file/folder outside of OneDrive.")
            if "Dropbox" in str(self.params[i].valueAsText):
                self.params[i].setErrorMessage("Value: " + str(self.params[i].valueAsText) + ". The file/folder is located inside a Dropbox folder. Please move the file/folder outside of Dropbox.")
