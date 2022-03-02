# NB-EntEx v1.0 - Nature Braid (NB) standalone code for entry/exit points

## Install and initialise NB_EE

1. Create a folder called NB_EE at the root of the C drive, or a local drive accessible to you. i.e. *C:\NB_EE*
2. Download or clone the NB_EE repository into the folder you created in step 1.
3. Open ArcMap.
4. In the *Catalog* window, connect to the NB_EE folder using the *Connect to Folder* icon. Within this folder is the **NB_EE.pyt** Python toolbox.
5. Expand the **NB_EE.pyt** toolbox and open the *Initialise toolbox* tool. This tool will define the "scratch folder" which contains intermediate outputs from the tool. Set the input parameters as below:.
- *Scratch path (folder which will contain intermediate files):* This may automatically be populated with a path that reflects where the original NB_EE folder is stored. For example, if the toolbox path is *C:/NB_EE*, this parameter will automatically be filled in with *C:/NBscratch* since this folder must sit in the same location as NB_EE.
- *Use developer mode?* If you wish to make your own code changes, tick this box. This automatically refreshes the toolbox so any changes to the .py files are applied without needing to restart ArcMap.
- *Reset all settings to their default values:* Tick this if you wish to reset the settings.
6. Once the tool completes, the *user_settings.xml* file should have been created inside the *NB_EE* folder.