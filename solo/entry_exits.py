import arcpy
from arcpy.sa import Watershed, SnapPourPoint, Reclassify, RemapRange
import os
import NB_EE.lib.log as log
import NB_EE.lib.common as common
import NB_EE.lib.assign_stream_network_id as assign_stream_network_id

from NB_EE.lib.refresh_modules import refresh_modules
refresh_modules([log, common, assign_stream_network_id])

def function(outputFolder, studyMask, streamNetwork, facRaster, fdrRaster):

    '''
    Find stream end points which lie on the boundary of the study area mask.
    The watersheds for each point are also calculated if wanted.
    '''

    class StreamSeg:

        def __init__(self, ID, fromNode, toNode, shape, fromNodePoint, toNodePoint, streamNetworkID=None):
            self.ID = ID
            self.fromNode = fromNode
            self.toNode = toNode
            self.shape = shape
            self.fromNodePoint = fromNodePoint
            self.toNodePoint = toNodePoint
            self.streamNetworkID = streamNetworkID


    class StreamNetwork:

        def __init__(self, ID, soloNodes=[], startNodes=[], lastStreamSeg=None, lastNode=None, lastNodePoint=None, lastNodeSeg=None):
            self.ID = ID
            self.soloNodes = soloNodes
            self.startNodes = startNodes
            self.lastStreamSeg = lastStreamSeg
            self.lastNode = lastNode
            self.lastNodePoint = lastNodePoint
            self.lastNodeSeg = lastNodeSeg


    class StraightLineSeg:

        def __init__(self, StreamSegID, polyline, intersectingPoints=[]):
            self.StreamSegID = StreamSegID
            self.polyline = polyline
            self.intersectingPoints = intersectingPoints


    class NodeAndSegmentPair:

        def __init__(self, node, segmentId):
            self.node = node
            self.segmentId = segmentId


    class IntersectingPoint:

        def __init__(self, pointID, streamSeg, streamNetworkID, pointCoords, pointType, pointFAC):
            self.pointID = pointID
            self.streamSeg = streamSeg
            self.streamNetworkID = streamNetworkID
            self.pointCoords = pointCoords
            self.pointType = pointType
            self.pointFAC = pointFAC


    def getMaxValueFromCellAndSurrounds(pointX, pointY, cellSize, cellSizeUnits, spatRef, raster):

        ''' Find maximum raster value at this point and also the 8 cells surrounding it '''
        maxValueAtPoint = 0

        for xMultiplier in range(-1, 2):
            for yMultiplier in range(-1, 2):

                shiftedX = pointX + (cellSize * xMultiplier)
                shiftedY = pointY + (cellSize * yMultiplier)
                shiftedXY = str(shiftedX) + " " + str(shiftedY)
                rasterValueAtPoint = arcpy.GetCellValue_management(raster, shiftedXY).getOutput(0)

                if xMultiplier == 0 and yMultiplier == 0:
                    valueAtExactPoint = rasterValueAtPoint

                if rasterValueAtPoint != 'NoData':
                    rasterValueAtPoint = float(rasterValueAtPoint)
                    if rasterValueAtPoint > maxValueAtPoint:
                        maxValueAtPoint = rasterValueAtPoint

        polyBuffer = os.path.join(arcpy.env.scratchGDB, "polyBuffer")

        # If value of exact point is NoData, then the point may lie exactly on the boundary of two raster cells,
        # which leads to spurious results from above calcs. Hence, we use a buffer around the point instead.
        if valueAtExactPoint == 'NoData':

            # Create buffer around point
            if arcpy.ProductInfo() == "ArcServer":
                pointFC = os.path.join(arcpy.env.scratchGDB, "pointFC")
                arcpy.CreateFeatureclass_management(arcpy.env.scratchGDB, "pointFC", 'POINT', spatial_reference=spatRef)
            else:
                pointFC = "in_memory/pointFC"
                arcpy.CreateFeatureclass_management("in_memory", "pointFC", 'POINT', spatial_reference=spatRef)

            # Add a zone field
            arcpy.AddField_management(pointFC, "ZONE", "SHORT")

            # Write point to a feature class
            insertCursor = arcpy.da.InsertCursor(pointFC, ["SHAPE@X", "SHAPE@Y", "ZONE"])
            row = (pointX, pointY, 0)
            insertCursor.insertRow(row)
            del insertCursor

            # Buffer the point by the cellsize
            arcpy.Buffer_analysis(pointFC, polyBuffer, str(cellSize * 1.5) + " " + cellSizeUnits)

            # Reset mask and extent environment variables as they can produce errors that made Zonal Stats fail
            arcpy.ClearEnvironment("extent")
            arcpy.ClearEnvironment("mask")

            outZonalStats = arcpy.sa.ZonalStatistics(polyBuffer, "ZONE", raster, "MAXIMUM", "DATA")
            outZonalStats.save(zonalStats)
            arcpy.CalculateStatistics_management(zonalStats)
            maxValueAtPoint = arcpy.GetRasterProperties_management(zonalStats, "MAXIMUM").getOutput(0)

            if maxValueAtPoint == 'NoData':
                maxValueAtPoint = 0
            else:
                maxValueAtPoint = int(maxValueAtPoint)

            arcpy.Delete_management(pointFC)
            arcpy.Delete_management(polyBuffer)

        return maxValueAtPoint


    def polygonToPolyline(polygon, polyline):

        '''
        Converts a polygon to a polyline.
        Used when advanced licence (and hence PolygonToLine_management tool) is not available.
        '''

        featuresList = []
        # Loop through each feature to fetch coordinates
        for row in arcpy.da.SearchCursor(polygon, ["SHAPE@"]):

            featurePartsList = []
            # Step through each part of the feature
            for part in row[0]:

                featurePointsList = []
                # Step through each vertex in the feature
                for pnt in part:

                    if pnt:
                        # Add x,y coordinates of current point to feature list
                        featurePointsList.append([pnt.X, pnt.Y])

                featurePartsList.append(featurePointsList)

            featuresList.append(featurePartsList)

        # Create Polylines
        features = []
        for feature in featuresList:

            # Create a Polyline object based on the array of points
            # Append to the list of Polyline objects
            for part in feature:
                features.append(
                    arcpy.Polyline(
                        arcpy.Array([arcpy.Point(*coords) for coords in part])))

        # Persist a copy of the Polyline objects using CopyFeatures
        arcpy.CopyFeatures_management(features, polyline)
        
        # Set the Polyline's spatial reference
        spatialRef = arcpy.Describe(polygon).spatialReference
        if spatialRef is not None:
            arcpy.DefineProjection_management(polyline, spatialRef)


    def pointWithinPolygonFC(point, polygonFC):

        '''Determine if point is within polygon feature class'''

        spatialRef = arcpy.Describe(polygonFC).spatialReference
        pointGeom = arcpy.PointGeometry(point, spatialRef)

        inside = False
        with arcpy.da.SearchCursor(polygonFC, ["SHAPE@"]) as searchCursor:

            for poly in searchCursor:
                polygonGeom = poly[0]

                # Check if the point lies within the polygon
                if not inside:
                    inside = pointGeom.within(polygonGeom)

        return inside


    def assignTypesToPoints(straightLineSeg, spatialRef):

        '''
        Assigns 'Entry' or 'Exit' to point type property of each intersecting point.
        As there may be more than more than one intersecting point lying on a straight line segment,
        this will affect if points are entry or exit points.
        '''

        # Find details about straight line segment
        firstPoint = straightLineSeg.polyline.firstPoint
        lastPoint = straightLineSeg.polyline.lastPoint

        # Find if these points lie inside or outside the study area
        firstPointInside = pointWithinPolygonFC(firstPoint, studyAreaMaskDissolved)
        lastPointInside = pointWithinPolygonFC(lastPoint, studyAreaMaskDissolved)

        # Find the flow accumulation at each of these points and determine which has the max flow
        firstXY = str(firstPoint.X) + " " + str(firstPoint.Y)
        lastXY = str(lastPoint.X) + " " + str(lastPoint.Y)

        firstFAC = arcpy.GetCellValue_management(hydFAC, firstXY).getOutput(0)
        lastFAC = arcpy.GetCellValue_management(hydFAC, lastXY).getOutput(0)
        maxFAC = max(firstFAC, lastFAC)

        if firstFAC != 'NoData':
            firstFAC = int(firstFAC)

        if lastFAC != 'NoData':
            lastFAC = int(lastFAC)

        # Get the geometry of the start and end points
        firstPointGeom = arcpy.PointGeometry(firstPoint, spatialRef)
        lastPointGeom = arcpy.PointGeometry(lastPoint, spatialRef)

        # If only one intersecting point falls on straight line segment
        if len(straightLineSeg.intersectingPoints) == 1:

            pointID = straightLineSeg.intersectingPoints[0]
            pointCoords = intersectPointsList[pointID].pointCoords

            # Check that both points are not inside or outside the polygon.
            # If they are then the intersecting point is at a vertex 
            if firstPointInside and lastPointInside or (not firstPointInside and not lastPointInside):
                pointType = "Touches" # Unlikely but possible
            else:
                if firstFAC == lastFAC:
                    pointType = "Cannot determine"
                else:
                    maxFACPoint = None

                    if maxFAC == firstFAC:
                        maxFACPoint = firstPoint
                        inside = firstPointInside
                    else:
                        maxFACPoint = lastPoint
                        inside = lastPointInside

                    if inside:
                        pointType = "Entry"
                    else:
                        pointType = "Exit"
            
            # Set the point's pointType property
            intersectPointsList[pointID].pointType = pointType

        # If two or more intersecting points fall on straight line segment
        elif len(straightLineSeg.intersectingPoints) >= 2:

            log.info('More than one intersecting point on this straight line segment')            

            # Order points so that point closest to the first point is at the top of the list,
            # and the point furthest from it is at the end of the list.
            orderedPoints = []
            for pointID in straightLineSeg.intersectingPoints:

                # Get intersecting point's geometry
                pointCoords = intersectPointsList[pointID].pointCoords
                pointGeom = arcpy.PointGeometry(arcpy.Point(pointCoords[0], pointCoords[1]), spatialRef)

                # Find distance from intersecting point to first point
                distanceFromFirstPoint = firstPointGeom.distanceTo(pointGeom)
                orderedPoints.append((pointID, distanceFromFirstPoint))

            # Sort the points into (distance from first point) order
            orderedPoints.sort(key=lambda x: x[1])

            # Loop through intersection points
            for i in range(0, len(orderedPoints)):

                # Assign the point type to the intersection point closest to the first point
                if i == 0:
                    
                    if maxFAC == firstFAC:
                        if firstPointInside:
                            pointType = 'Entry'
                        else:
                            pointType = 'Exit'
                    else:
                        if firstPointInside:
                            pointType = 'Exit'
                        else:
                            pointType = 'Entry'

                # Then alternate between entry and exit points
                else:
                    prevPointType = pointType
                    if prevPointType == 'Exit':
                        pointType = 'Entry'
                    else:
                        pointType = 'Exit'

                # Set the point's pointType property
                pointID = orderedPoints[i][0]
                intersectPointsList[pointID].pointType = pointType    


    def createStraightLineSegments(streamSegments):

        # Break up each of the segments in the streamSegments list into its straight line components.
        # Store these straight line segments in straightLineSegments list.
        straightLineSegments = []
        for streamSeg in streamSegments:

            shape = streamSeg.shape

            # Step through each part of the feature
            for part in shape:

                prevX = None
                prevY = None

                # Step through each vertex in the feature
                for pnt in part:
                    if pnt:
                        if prevX:
                            array = arcpy.Array([arcpy.Point(prevX, prevY), arcpy.Point(pnt.X, pnt.Y)])
                            polyline = arcpy.Polyline(array)
                            straightLineSegments.append(StraightLineSeg(streamSeg.ID, polyline))

                        prevX = pnt.X
                        prevY = pnt.Y
                    else:
                        # If pnt is None, this represents an interior ring
                        log.info("Interior Ring:")

        return straightLineSegments


    def findTerminalNodesForStreamNetworks(streamSegments):

        # Find start and end (solo) nodes for each stream network
        # The solo nodes only appear once (hence solo)
        streamNetworks = []
        for i in range(1, maxStreamNetworkID + 1):

            soloNodes = []
            manyNodes = []

            for streamSeg in streamSegments:
                if streamSeg.streamNetworkID == i:

                    nodePair = [streamSeg.fromNode, streamSeg.toNode]

                    # Add the node to soloNodes or manyNodes lists. It can only be in one of these lists.
                    for node in nodePair:

                        # Find if node is in soloNodes list
                        inSoloNodes = False
                        for nodeSeg in soloNodes:
                            if nodeSeg.node == node:
                                soloNodesIndex = soloNodes.index(nodeSeg)
                                inSoloNodes = True

                        inManyNodes = node in manyNodes

                        if inSoloNodes:
                            # Remove node from list
                            del soloNodes[soloNodesIndex]

                            # Add node to manyNodes
                            manyNodes.append(node)

                        if not inSoloNodes and not inManyNodes:
                            soloNodes.append(NodeAndSegmentPair(node, streamSeg.ID))

            streamNetworks.append(StreamNetwork(i, soloNodes))

        return streamNetworks


    def findFirstEntryPoint(streamSeg):

        entryPointsOnStreamSeg = []

        # Loop through intersecting points, looking for the entry point which lies on this stream segment
        for id in range(1, len(intersectPointsList)):

            intersectPoint = intersectPointsList[id]
            if intersectPoint.streamSeg == streamSeg.ID and intersectPoint.pointType == 'Entry':
                entryPointsOnStreamSeg.append(intersectPoint)

        if len(entryPointsOnStreamSeg) > 0:

            # Sort the entry points so that lowest FAC comes first
            entryPointsOnStreamSeg.sort(key=lambda x: x.pointFAC)
            firstEntryPoint = entryPointsOnStreamSeg[0]

        else:
            log.warning('Could not find first entry point which should exist on stream segment ' + str(streamSeg.ID))
            firstEntryPoint = None

        return firstEntryPoint


    #############################
    ### Main code starts here ###
    #############################

    try:
        # Reset mask and extent environment variables
        arcpy.ClearEnvironment("extent")
        arcpy.ClearEnvironment("mask")

        hydFAC = facRaster
        streams = streamNetwork
        studyAreaMask = studyMask
        hydFDR = fdrRaster

        # Initialise temporary variables
        prefix = os.path.join(arcpy.env.scratchGDB, "exit_")
        
        studyAreaMaskDissolved = prefix + "studyAreaMaskDissolved"
        streamsCopy = prefix + "streamsCopy"
        intersectPoints = prefix + "intersectPoints"
        zonalStats = prefix + "zonalStats"
        boundaryLine = prefix + "boundaryLine"
        intersectMultiPoints = prefix + "intersectMultiPoints"

        # Initialise output variables
        entryExitPoints = os.path.join(outputFolder, 'entryexits.shp')
        streamNetworkFC = os.path.join(outputFolder, 'streamnetwork.shp')

        # Get cell size of raster
        cellSize = float(arcpy.GetRasterProperties_management(hydFAC, "CELLSIZEX").getOutput(0))

        # Find cellSize units
        spatialRefFAC = arcpy.Describe(hydFAC).spatialReference
        cellSizeUnits = spatialRefFAC.linearUnitName

        # Find polygon spatial reference
        spatialRefStreams = arcpy.Describe(streams).spatialReference

        # Make a copy of streams file as it will be amended
        arcpy.CopyFeatures_management(streams, streamsCopy)

        # Create a dictionary, with the index being the stream node number and the value being the number of times
        # it appears in the feature class
        nodeCounts = {}
        with arcpy.da.SearchCursor(streamsCopy, ["FROM_NODE", "TO_NODE"]) as searchCursor:

            for row in searchCursor:

                fromNode = int(row[0])
                toNode = int(row[1])
                nodePair = [fromNode, toNode]

                for node in nodePair:
                    if node in nodeCounts:
                        nodeCounts[node] += 1
                    else:
                        nodeCounts[node] = 1

        # Populate stream segments list, so can access quicker and easier than using search cursors
        streamSegments = []
        streamSegID = 0
        arcpy.AddField_management(streamsCopy, "SEGMENT_ID", "LONG")
        
        with arcpy.da.UpdateCursor(streamsCopy, ["FROM_NODE", "TO_NODE", "SHAPE@", "SEGMENT_ID"]) as updateCursor:

            for row in updateCursor:

                fromNode = int(row[0])
                toNode = int(row[1])
                shape = row[2]
                fromNodePoint = shape.firstPoint
                toNodePoint = shape.lastPoint

                # Include stream segments which have both end points within the study area mask boundary
                # Also include stream segment is not connected to any other stream segments
                if (pointWithinPolygonFC(fromNodePoint, studyAreaMask)
                 or pointWithinPolygonFC(toNodePoint, studyAreaMask)
                 or nodeCounts[fromNode] > 1
                 or nodeCounts[toNode] > 1):

                    row[3] = streamSegID
                    streamSegments.append(StreamSeg(streamSegID, fromNode, toNode, shape, fromNodePoint, toNodePoint))
                    streamSegID += 1
                    updateCursor.updateRow(row)

                else:
                    updateCursor.deleteRow()

        ###################
        ### Exit points ###
        ###################

        # Dissolve the study area mask
        arcpy.Dissolve_management(studyAreaMask, studyAreaMaskDissolved)

        # Create boundary line polyline from dissolved study area mask
        if common.checkLicenceLevel('Advanced'):
            arcpy.PolygonToLine_management(studyAreaMaskDissolved, boundaryLine, "IGNORE_NEIGHBORS")
        else:
            log.info("Advanced licence not available. Using alternative function to generate boundary line.")
            polygonToPolyline(studyAreaMaskDissolved, boundaryLine)

        # Find all points where streams intersect the boundary line. The intersection points are multipoints (i.e. multiple points per line segment)
        arcpy.Intersect_analysis([streamsCopy, boundaryLine], intersectMultiPoints, output_type="POINT")

        # Convert the multi points to single points
        arcpy.MultipartToSinglepart_management(intersectMultiPoints, intersectPoints)
        noIntersectPoints = int(arcpy.GetCount_management(intersectPoints).getOutput(0))

        intPtsCopy = prefix + 'intPtsCopy'
        arcpy.CopyFeatures_management(intersectPoints, intPtsCopy)

        ############################################################
        ### Find if intersection points are entry or exit points ###
        ############################################################

        '''
        To do this we need to find out which stream segment the points lie on,
        then break this stream segment shape into its component vertices and create line segments from these vertices.
        We then find out which line segment the intersection point lies on.
        We then check this line segment's vertices to find out which has a higher flow accumulation.
        If this vertex is inside the farm boundary then it is an entry point, otherwise an exit point.
        Loop through the straight line segments to find if intersection points that lie on them are entry or exit points.
        '''

        log.info('Creating stream network feature class, with one row per stream')
        streamSegments, maxStreamNetworkID = assign_stream_network_id.function(streamsCopy, streamNetworkFC, "FROM_NODE", "TO_NODE", streamSegments)

        log.info('Finding intersection points')

        if noIntersectPoints == 0:
            log.warning('No entry or exit points found')
            entryExitPoints = None

        else:
            log.info('Populate intersection points list')

            # Create and populate intersection points list
            # + 1 in the following line as the OBJECTID column in intersectPoints feature class starts at 1. The zeroth index is unused.
            intersectPointsList = [None] * (noIntersectPoints + 1)
            with arcpy.da.SearchCursor(intersectPoints, ["OBJECTID", "SEGMENT_ID", "SHAPE@XY"]) as searchCursor:

                for pt in searchCursor:

                    pointID = pt[0]
                    streamSeg = pt[1]
                    pointCoords = pt[2]

                    pointCoordsXY = str(pointCoords[0]) + " " + str(pointCoords[1])
                    streamNetworkID = streamSegments[streamSeg].streamNetworkID
                    pointFAC = getMaxValueFromCellAndSurrounds(pointCoords[0], pointCoords[1], cellSize, cellSizeUnits, spatialRefStreams, hydFAC)

                    intersectPointsList[pointID] = IntersectingPoint(pointID, streamSeg, streamNetworkID, pointCoords, '', pointFAC)

            # Break up polylines into their component straight line segments
            straightLineSegments = createStraightLineSegments(streamSegments)

            # Create list of straight line segments which have intersection points lying on them
            log.info('Create list of straight line segments which have intersection points lying on them')
            intersectingStraightLines = []
            for lineSeg in straightLineSegments:

                for point in intersectPointsList:

                    if point is not None: # it will be None if the zeroth index in the list is unused

                        pointID = point.pointID
                        streamSegID = point.streamSeg
                        pointCoords = point.pointCoords                        

                        if lineSeg.StreamSegID == streamSegID:

                            intersectPoint = arcpy.Point(pointCoords[0], pointCoords[1])
                            intersectPointGeom = arcpy.PointGeometry(intersectPoint)

                            lineSegGeom = lineSeg.polyline
                            if lineSegGeom.contains(intersectPointGeom):

                                # Add intersecting point ID to the 
                                lineSeg.intersectingPoints = lineSeg.intersectingPoints + [pointID]

                # Add to list
                if len(lineSeg.intersectingPoints) > 0:
                    intersectingStraightLines.append(lineSeg)

            log.info('Find if intersection points are entry or exit points')

            if len(intersectingStraightLines) == 0:

                # If there are no stream segments with entry/exit points
                log.warning('No entry/exit points found')
                return None, streamNetworkFC

            else:
                for straightLineSeg in intersectingStraightLines:
                    assignTypesToPoints(straightLineSeg, spatialRefStreams)

            ###############################################
            ### Remove superfluous entry or exit points ###
            ###############################################

            '''
            We primarily want to show the main exit point, smaller exit points, and entry.
            Often, especially if a stream runs along the boundary line of the study area then
            additional entry and exit points are generated.

            The point removal functions do the following:
                1. Mark points that are within a distance threshold of each other.
                2. Remove all marked exit points, and remove all entry points apart from those marked as ones to keep.

            '''

            # First, find the entry and exit points for each stream network
            streamNetEntryPoints = {}
            streamNetExitPoints = {}

            for id in range(1, len(intersectPointsList)):
                pt = intersectPointsList[id]

                if pt.pointType == 'Entry':
                    if pt.streamNetworkID in streamNetEntryPoints:
                        streamNetEntryPoints[pt.streamNetworkID].append(pt)
                    else:
                        streamNetEntryPoints[pt.streamNetworkID] = [pt]

                if pt.pointType == 'Exit':
                    if pt.streamNetworkID in streamNetExitPoints:
                        streamNetExitPoints[pt.streamNetworkID].append(pt)
                    else:
                        streamNetExitPoints[pt.streamNetworkID] = [pt]
            
            # Work out which entry and exit points to keep (as streams may weave along the study area mask boundary).
            # We only want the last exit point and the first entry point on each stream branch.
            pointsToRemove = []
            entryPointsToKeep = []

            # For each stream network, find the exit point with the maximum flow accumulation
            # Mark all other exit points as points to be removed
            for streamNetworkID in streamNetExitPoints:
                maxExitPoint = max(streamNetExitPoints[streamNetworkID], key=lambda item: item.pointFAC)

            # Find start and end (solo) nodes for each stream network
            streamNetworks = findTerminalNodesForStreamNetworks(streamSegments)

            # Find last stream segment and node of each stream network (i.e. towards end of stream)
            for streamNetwork in streamNetworks:

                maxFAC = 0
                for nodeSeg in streamNetwork.soloNodes:

                    node = nodeSeg.node
                    segID = nodeSeg.segmentId

                    # Find the node's point
                    if streamSegments[segID].fromNode == node:
                        point = streamSegments[segID].fromNodePoint
                    else:
                        point = streamSegments[segID].toNodePoint

                    # Find the flow accumulation at this point
                    maxFlowAccAtPoint = getMaxValueFromCellAndSurrounds(point.X, point.Y, cellSize, cellSizeUnits, spatialRefStreams, hydFAC)

                    if maxFlowAccAtPoint >= maxFAC:
                        maxFAC = maxFlowAccAtPoint
                        maxFACStreamSegID = segID
                        maxFACNode = node
                        maxFACPoint = point
                        maxFACNodeSeg = nodeSeg

                streamNetwork.lastStreamSeg = maxFACStreamSegID
                streamNetwork.lastNode = maxFACNode
                streamNetwork.lastNodePoint = maxFACPoint
                streamNetwork.lastNodeSeg = maxFACNodeSeg

            # Populate the entryPointsToKeep array initially with all entry points
            for streamNetworkID in streamNetEntryPoints:
                for pt in streamNetEntryPoints[streamNetworkID]:
                    entryPointsToKeep.append(pt.pointID)

            ### Find pairs of entry/exit points that are close together and have similar flow accumulation values ###

            # Loop through coords list to find pairs of points that are less than the threshold distance apart
            distanceThresh = 100
            spatialRef = arcpy.Describe(intersectPoints).spatialReference

            for id1 in range(1, len(intersectPointsList)):

                pt1 = intersectPointsList[id1]
                pt1Geom = arcpy.PointGeometry(arcpy.Point(pt1.pointCoords[0], pt1.pointCoords[1]), spatialRef)

                if id1 < len(intersectPointsList):
                    for id2 in range(id1 + 1, len(intersectPointsList)):

                        pt2 = intersectPointsList[id2]
                        if ((pt1.pointType == 'Entry' and pt2.pointType == 'Exit') or (pt1.pointType == 'Exit' and pt2.pointType == 'Entry')):

                            pt2Geom = arcpy.PointGeometry(arcpy.Point(pt2.pointCoords[0], pt2.pointCoords[1]), spatialRef)
                            distanceBetweenPoints = pt1Geom.distanceTo(pt2Geom)

                            ## Future improvement: what is the threshold for "similarity"?

                            if distanceBetweenPoints < distanceThresh:
                                if pt1.pointID not in pointsToRemove:
                                    pointsToRemove.append(pt1.pointID)
                                                                    
                                if pt2.pointID not in pointsToRemove:
                                    pointsToRemove.append(pt2.pointID)
                                    
            # Find the exit point with the maximum FAC. First create list of exit points.
            exitPointsList = []
            for id in range(1, len(intersectPointsList)):
                pt = intersectPointsList[id]
                if pt.pointType == 'Exit':
                    exitPointsList.append(pt)

            # Find the point with the maximum overall flow accumulation
            maxExitPoint = max(exitPointsList, key=lambda item: item.pointFAC)
            
            # Update this point with a point type of 'Main exit'
            intersectPointsList[maxExitPoint.pointID].pointType = 'Main exit'

            # Update the intersecting points feature class with the point types, point numbers and stream network numbers.
            log.info('Update the intersecting points feature class with the point types')            
            arcpy.AddField_management(intersectPoints, "POINT_NO", "LONG")
            arcpy.AddField_management(intersectPoints, "POINT_TYPE", "TEXT")
            arcpy.AddField_management(intersectPoints, "STREAM_NO", "LONG")
            pointNo = 1
            with arcpy.da.UpdateCursor(intersectPoints, ["OBJECTID", "SEGMENT_ID", "SHAPE@XY", "POINT_NO", "POINT_TYPE", "STREAM_NO"]) as updateCursor:

                for pt in updateCursor:
                    pointID = pt[0]
                    streamSeg = pt[1]
                    pointCoords = pt[2]

                    pt[3] = pointNo
                    pt[4] = intersectPointsList[pointID].pointType
                    pt[5] = intersectPointsList[pointID].streamNetworkID

                    if pointID in pointsToRemove and pointID != maxExitPoint.pointID:                        
                        updateCursor.deleteRow()
                    else:
                        if intersectPointsList[pointID].pointType == 'Entry' and pointID not in entryPointsToKeep:                            
                            updateCursor.deleteRow()
                            
                        else:
                            updateCursor.updateRow(pt)

                    pointNo += 1

            # Write intersection point feature class to disk
            arcpy.CopyFeatures_management(intersectPoints, entryExitPoints)

        #########################
        ### Create watersheds ###
        #########################

        streamEnds = os.path.join(arcpy.env.scratchWorkspace, prefix + "streamEnds")
        watershedsPoly = prefix + "watershedsPoly"
        watershedsFC = os.path.join(outputFolder, "watersheds.shp")

        # Create stream ends feature class
        arcpy.CreateFeatureclass_management(os.path.dirname(streamEnds), os.path.basename(streamEnds), 'POINT', spatial_reference=spatialRefStreams)

        # Add stream no field
        arcpy.AddField_management(streamEnds, "STREAM_NO", "LONG")
        
        # Write stream end points to a feature class (used when calculating the watersheds)
        insertCursor = arcpy.da.InsertCursor(streamEnds, ["SHAPE@X", "SHAPE@Y", "STREAM_NO"])
        for stream in streamNetworks:
            point = (stream.lastNodePoint.X, stream.lastNodePoint.Y, stream.ID)
            insertCursor.insertRow((point))
        del insertCursor

        log.info("Determining watershed for each of the streams in the stream network")

        # Snap pour points (stream ends) to surrounding cell with highest flow accumulation
        pourPoints = SnapPourPoint(streamEnds, hydFAC, cellSize * 1.5, "STREAM_NO")

        # Calculate watersheds from pour points
        watersheds = Watershed(hydFDR, pourPoints)

        # Convert watersheds raster to feature class
        arcpy.RasterToPolygon_conversion(watersheds, watershedsPoly, "NO_SIMPLIFY")

        # 'Rename' gridcode column to STREAM_NO
        arcpy.AddField_management(watershedsPoly, "STREAM_NO", "LONG")
        with arcpy.da.UpdateCursor(watershedsPoly, ["gridcode", "STREAM_NO"]) as updateCursor:
            for row in updateCursor:
                row[1] = row[0]
                updateCursor.updateRow(row)

        arcpy.DeleteField_management(watershedsPoly, "gridcode")

        # Dissolve watersheds poly
        arcpy.Dissolve_management(watershedsPoly, watershedsFC, "STREAM_NO")

        return entryExitPoints, streamNetworkFC, watershedsFC

    except Exception:
        log.error("Critical exit point operations did not complete successfully")
        raise
