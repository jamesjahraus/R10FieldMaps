r"""ArcGIS Pro setup to automate the execution of geoprocessing tools.

Author: https://github.com/jamesjahraus

ArcGIS Pro Python reference:
https://pro.arcgis.com/en/pro-app/latest/arcpy/main/arcgis-pro-arcpy-reference.htm
"""

import os
import sys
import time
import csv
import requests
import arcpy
from bs4 import BeautifulSoup


def pwd():
    r"""Prints the working directory.
    Used to determine the directory this module is in.

    Returns:
        The path of the directory this module is in.
    """
    wd = sys.path[0]
    arcpy.AddMessage('wd: {0}'.format(wd))
    return wd


def set_path(wd, data_path):
    r"""Joins a path to the working directory.

    Arguments:
        wd: The path of the directory this module is in.
        data_path: The suffix path to join to wd.
    Returns:
        The joined path.
    """
    path_name = os.path.join(wd, data_path)
    arcpy.AddMessage('path_name: {0}'.format(path_name))
    return path_name


def import_spatial_reference(dataset):
    r"""Extracts the spatial reference from input dataset.

    Arguments:
        dataset: Dataset with desired spatial reference.
    Returns:
        The spatial reference of any dataset input.
    """
    spatial_reference = arcpy.Describe(dataset).spatialReference
    arcpy.AddMessage('spatial_reference: {0}'.format(spatial_reference.name))
    return spatial_reference


def setup_env(workspace_path, spatial_ref_dataset):
    # Set workspace path.
    arcpy.env.workspace = workspace_path
    arcpy.AddMessage('workspace(s): {}'.format(arcpy.env.workspace))

    # Set output overwrite option.
    arcpy.env.overwriteOutput = True
    arcpy.AddMessage('overwriteOutput: {}'.format(arcpy.env.overwriteOutput))

    # Set the output spatial reference.
    arcpy.env.outputCoordinateSystem = import_spatial_reference(
        spatial_ref_dataset)
    arcpy.AddMessage('outputCoordinateSystem: {}'.format(
        arcpy.env.outputCoordinateSystem.name))


def check_status(result):
    r"""Logs the status of executing geoprocessing tools.

    Requires futher investigation to refactor this function:
        I can not find geoprocessing tool name in the result object.
        If the tool name can not be found may need to pass it in.
        Return result.getMessages() needs more thought on what it does.

    Understanding message types and severity:
    https://pro.arcgis.com/en/pro-app/arcpy/geoprocessing_and_python/message-types-and-severity.htm

    Arguments:
        result: An executing geoprocessing tool object.
    Returns:
        Requires futher investigation on what result.getMessages() means on return.
    """
    status_code = dict([(0, 'New'), (1, 'Submitted'), (2, 'Waiting'),
                        (3, 'Executing'), (4, 'Succeeded'), (5, 'Failed'),
                        (6, 'Timed Out'), (7, 'Canceling'), (8, 'Canceled'),
                        (9, 'Deleting'), (10, 'Deleted')])

    arcpy.AddMessage('current job status: {0}-{1}'.format(
        result.status, status_code[result.status]))
    # Wait until the tool completes
    while result.status < 4:
        arcpy.AddMessage('current job status (in while loop): {0}-{1}'.format(
            result.status, status_code[result.status]))
        time.sleep(0.2)
    messages = result.getMessages()
    arcpy.AddMessage('job messages: {0}'.format(messages))
    return messages


def parse_geoid18_response(html):
    r"""Parse a successful response to noaa geoid18 calculator

    See:
    https://geodesy.noaa.gov/GEOID/GEOID18/computation.html

    Arguments:
        html: Valid html page from a successful response from noaa geoid18 calculator
    Returns:
        Geoid undulation N and the error e
    """
    soup = BeautifulSoup(html, 'html.parser')
    n = soup.pre.string
    lines = n.split('\n')
    data = lines[3].split()
    n = float(data[-2])
    e = float(data[-1])
    arcpy.AddMessage(f'data from geoid18: {data}')
    arcpy.AddMessage(f'N: {n}')
    arcpy.AddMessage(f'error: {e}')
    return n, e


def postprocess_geoid18(lat, long, h):
    r"""# Postprocess Geoid18 Elevations from Ellipsoid height to Orthometric using noaa geoid18 calculator
    https://geodesy.noaa.gov/GEOID/GEOID18/computation.html
    https://geodesy.noaa.gov/cgi-bin/GEOID_STUFF/geoid18_single.prl?PGM=intg&MODEL=14&LAT=40.050689&LONG=105.281975&longitude_direction=2

    https://pro.arcgis.com/en/pro-app/3.0/help/mapping/properties/geoid.htm
    Ellipsoid height = h
    Geoid undulation = N
    Orthometric height = H
    h = H + N
    H = h - N

    Arguments:
        lat: Latitude
        long: Longitude
        h: Ellipsoid height
    Returns:
        Orthometric height
    """
    url = f'https://geodesy.noaa.gov/cgi-bin/GEOID_STUFF/geoid18_single.prl?PGM=intg&MODEL=14&LAT={lat}&LONG={long}&longitude_direction=2'
    r = requests.get(url)
    arcpy.AddMessage(f'request to noaa geoid18 status: {r.status_code}')
    html_file = r.content.decode('UTF-8')
    n = parse_geoid18_response(html_file)[0]
    orthometric_height = h - n
    arcpy.AddMessage(f'Orthometric height, H = h - N, {orthometric_height} = {h} - {n}')
    return orthometric_height


def transform():
    """Transforms R10Points.csv
    Transforms R10Points.csv to orthometric_R10Points.csv using postprocess_geoid18 function
    Returns:
        ./Data/orthometric_R10Points.csv
    """
    arcpy.AddMessage('Transforming points to orthometric using postprocess_geoid18 function')
    data_path = set_path(pwd(), 'Data')
    csv_path = set_path(data_path, 'R10Points.csv')
    new_csv_path = set_path(data_path, 'orthometric_R10Points.csv')
    rh = 1.55  # the rod height is 1.55 m
    with open(new_csv_path, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['Name', 'Ortho_Measured', 'ReceiverName', 'HorizontalAccuracy', 'VerticalAccuracy',
                      'Latitude', 'Longitude', 'Elevation', 'NumberSatellites', 'FixTime', 'Measured_Ortho',
                      'Calculated_Ortho']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        with open(csv_path, 'r') as point_reader:
            csv_dict = csv.DictReader(point_reader, delimiter=',')
            for row in csv_dict:
                lat = float(row.get('Latitude'))
                long = abs(float(row.get('Longitude')))
                elev = float(row.get('Elevation'))
                calculated_ortho = postprocess_geoid18(lat, long, elev)
                measured_ortho = float(row.get('Ortho_Measured')) - rh
                row_dict = {'Name': row.get('Name'),
                            'Ortho_Measured': row.get('Ortho_Measured'), 'ReceiverName': row.get('ReceiverName'),
                            'HorizontalAccuracy': row.get('HorizontalAccuracy'),
                            'VerticalAccuracy': row.get('VerticalAccuracy'),
                            'Latitude': row.get('Latitude'), 'Longitude': row.get('Longitude'),
                            'Elevation': row.get('Elevation'), 'NumberSatellites': row.get('NumberSatellites'),
                            'FixTime': row.get('FixTime'), 'Measured_Ortho': measured_ortho,
                            'Calculated_Ortho': f'{calculated_ortho:0.2f}'}
                arcpy.AddMessage(f'Writing row to orthometric_R10Points.csv: {row_dict}')
                writer.writerow(row_dict)


def main():
    r"""Postprocess Ellipsoid to Orthometric and Generate a Point Feature Class for Analysis

    Data collected is assumed to use Geoid18 Conus.

    Orthometric heights calculated using noaa geoid18 calculator service.
    H = h - N
    https://geodesy.noaa.gov/GEOID/GEOID18/computation.html

    String to format Point Feature Class
    "Measured: " + $feature.Measured_Ortho + " (m)" + TextFormatting.NewLine + TextFormatting.NewLine + "Calculated: " + $feature.Calculated_Ortho + " (m)"
    """
    # Setup Geoprocessing Environment
    spatial_ref_dataset = 'usgs_dem_05m'
    wd = pwd()
    db = set_path(wd, 'R10FieldMaps.gdb')
    setup_env(db, spatial_ref_dataset)
    data_path = set_path(pwd(), 'Data')
    csv_file = set_path(data_path, 'orthometric_R10Points.csv')
    file_name = 'orthometric_R10Points'

    # Postprocess Ellipsoid to Orthometric
    transform()

    # Generate a Point Feature Class for Analysis
    generate_points = arcpy.management.XYTableToPoint(csv_file, file_name, 'Longitude', 'Latitude')
    check_status(generate_points)


if __name__ == '__main__':
    main()
