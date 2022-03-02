import arcpy
import os

import NB_EE.lib.log as log
from NB_EE.lib.refresh_modules import refresh_modules
refresh_modules([log])

def function(streams, streamNetworks, fromNodeField, toNodeField, streamSegments=[]):

    class StreamSeg:

        def __init__(self, ID, fromNode, toNode, streamNetworkID=None):
            self.ID = ID
            self.fromNode = fromNode
            self.toNode = toNode
            self.streamNetworkID = streamNetworkID


    #############################
    ### Create stream network ###
    #############################

    try:
        # Initialise temporary variables
        prefix = "genStrNet_"
        streamsCopy = os.path.join(arcpy.env.scratchFolder, prefix + "streamsCopy.shp")

        if streamSegments == []:

            # Populate stream segments list, so can access quicker and easier than using search cursors
            with arcpy.da.SearchCursor(streams, ["SEGMENT_ID", fromNodeField, toNodeField]) as searchCursor:

                for row in searchCursor:

                    streamSegID = row[0]
                    fromNode = int(row[1])
                    toNode = int(row[2])

                    streamSegments.append(StreamSeg(streamSegID, fromNode, toNode))

            log.info('Streams loaded into memory from file')
        
        # Sort stream segments list into from node order
        streamSegments.sort(key=lambda x: x.fromNode)

        # Create dictionary for 'from' nodes to make accessing them faster in loop later on
        fromNodeDict = {}
        prevNode = -1
        IDlist = []

        for streamSeg in streamSegments:
            currNode = streamSeg.fromNode

            if currNode == prevNode:
                IDlist.append(streamSeg.ID)
            else:
                fromNodeDict[prevNode] = IDlist
                IDlist = [streamSeg.ID]

            prevNode = currNode

        # Write last node to dictionary
        fromNodeDict[prevNode] = IDlist

        # Sort stream segments list into to node order
        streamSegments.sort(key=lambda x: x.toNode)

        # Create dictionary for 'to' nodes to make accessing them faster in loop later on
        toNodeDict = {}
        prevNode = -1
        IDlist = []

        for streamSeg in streamSegments:
            currNode = streamSeg.toNode

            if currNode == prevNode:
                IDlist.append(streamSeg.ID)
            else:
                toNodeDict[prevNode] = IDlist
                IDlist = [streamSeg.ID]

            prevNode = currNode

        # Write last node to dictionary
        toNodeDict[prevNode] = IDlist

        # Sort stream segments back into ID order
        streamSegments.sort(key=lambda x: x.ID)

        # Loop through stream segments giving them a stream network ID
        log.info('Assigning stream network IDs to streams')
        streamNetworkID = 1
        streamNodes = []

        for streamSeg in streamSegments:

            if streamSeg.streamNetworkID is None:

                # Give stream segment SNID
                streamSeg.streamNetworkID = streamNetworkID

                # Add both nodes to stream nodes list
                streamNodes.append(streamSeg.fromNode)
                streamNodes.append(streamSeg.toNode)

                # While stream nodes list is not empty
                while len(streamNodes):

                    nodeToFind = streamNodes[0]

                    # Get all other segments with the matching node
                    linkedSegmentIDs = []

                    try:
                        linkedSegmentIDs += fromNodeDict[nodeToFind]
                    except KeyError:
                        pass

                    try:
                        linkedSegmentIDs += toNodeDict[nodeToFind]
                    except KeyError:
                        pass

                    for i in linkedSegmentIDs:

                        if streamSeg.ID != streamSegments[i].ID and streamSegments[i].streamNetworkID is None:

                            # Give segment a stream network ID
                            streamSegments[i].streamNetworkID = streamNetworkID

                            # Add new node to stream nodes list
                            endNodes = [streamSegments[i].fromNode, streamSegments[i].toNode]
                            endNodes.remove(nodeToFind)
                            streamNodes = streamNodes + endNodes

                    # Remove processed node from stream nodes list
                    streamNodes.pop(0)

                # Increment stream network ID
                streamNetworkID = streamNetworkID + 1

        maxStreamNetworkID = streamNetworkID - 1

        # Create copy of stream display shapefile
        arcpy.CopyFeatures_management(streams, streamsCopy)

        # Update streams file with stream network id
        log.info('Updating stream file with stream network ID')
        arcpy.AddField_management(streamsCopy, "STREAM_NO", "LONG")

        with arcpy.da.UpdateCursor(streamsCopy, ["SEGMENT_ID", "STREAM_NO"]) as updateCursor:

            for row in updateCursor:

                streamSegID = row[0]
                row[1] = streamSegments[streamSegID].streamNetworkID

                try:
                    updateCursor.updateRow(row)
                except Exception:
                    pass

        # Create streams shapefile, with one stream network per row
        log.info('Dissolving streams to create stream networks file')
        arcpy.Dissolve_management(streamsCopy, streamNetworks, ["STREAM_NO"], "", "MULTI_PART", "DISSOLVE_LINES")

        return streamSegments, maxStreamNetworkID

    except Exception:
        raise
