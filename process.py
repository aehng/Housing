import os
import pandas as pd
from pyproj import Transformer

try:
    import geopandas as gpd
    from shapely.geometry import Point
    GEOPANDAS_AVAILABLE = True
except ImportError:
    GEOPANDAS_AVAILABLE = False

# Initialize the transformer
# EPSG:2285 is Washington State Plane North (US Survey Feet)
# EPSG:4326 is standard WGS84 Latitude/Longitude
transformer = Transformer.from_crs("EPSG:2285", "EPSG:4326", always_xy=True)

SCHOOL_SHAPEFILE_ROOT = os.path.join('SABS_1516_SchoolLevels', 'SABS_1516_SchoolLevels')
SCHOOL_LAYERS = {
    'elementary': 'SABS_1516_Primary.shp',
    'middle': 'SABS_1516_Middle.shp',
    'high': 'SABS_1516_High.shp',
}


def convert_to_latlon(row):
    """Takes x, y and returns a Series with Longitude, Latitude."""
    try:
        lon, lat = transformer.transform(row['x'], row['y'])
        return pd.Series({'Longitude': lon, 'Latitude': lat})
    except Exception:
        return pd.Series({'Longitude': None, 'Latitude': None})


def convert_common_interest_points(input_csv='COMMON_INTEREST_POINT.csv', output_csv='converted_data.csv'):
    df = pd.read_csv(input_csv)
    print(f"Converting coordinates for {input_csv}...")
    df[['Longitude', 'Latitude']] = df.apply(convert_to_latlon, axis=1)
    print(df[['NAME', 'x', 'y', 'Latitude', 'Longitude']].head())
    df.to_csv(output_csv, index=False)
    print(f"Saved converted POI data to {output_csv}")
    return df


def _get_name_column(gdf):
    candidates = [c for c in gdf.columns if c.lower() in {'schnam', 'schoolname', 'name', 'schnm'}]
    return candidates[0] if candidates else None


def read_school_layer(shapefile_path):
    if not GEOPANDAS_AVAILABLE:
        raise ImportError('geopandas is required for school boundary joins. Install it with pip install geopandas shapely fiona')
    layer = gpd.read_file(shapefile_path)
    if layer.crs is None:
        raise ValueError(f'CRS not found for {shapefile_path}')
    return layer


def assign_school_boundaries_to_houses(houses_df, shapefile_root=SCHOOL_SHAPEFILE_ROOT):
    if not GEOPANDAS_AVAILABLE:
        raise ImportError('geopandas is required for school boundary joins. Install it with pip install geopandas shapely fiona')

    houses = houses_df.copy()
    if 'Longitude' not in houses.columns or 'Latitude' not in houses.columns:
        if 'long' in houses.columns and 'lat' in houses.columns:
            houses['Longitude'] = houses['long']
            houses['Latitude'] = houses['lat']
        else:
            raise ValueError('House dataframe must contain long/lat or Longitude/Latitude columns')

    houses_gdf = gpd.GeoDataFrame(
        houses,
        geometry=gpd.points_from_xy(houses['Longitude'], houses['Latitude']),
        crs='EPSG:4326',
    )

    for level, shapefile in SCHOOL_LAYERS.items():
        shapefile_path = os.path.join(shapefile_root, shapefile)
        if not os.path.exists(shapefile_path):
            raise FileNotFoundError(f'Shapefile not found: {shapefile_path}')

        print(f'Loading {level} school boundaries from {shapefile_path}...')
        layer = read_school_layer(shapefile_path)

        if layer.crs != houses_gdf.crs:
            layer = layer.to_crs(houses_gdf.crs)

        name_col = _get_name_column(layer)
        if name_col is None:
            raise ValueError(f'No name column found in {shapefile_path}. Expected schnam, schoolname, name, or similar.')

        layer = layer[[name_col, 'geometry']].rename(columns={name_col: f'assigned_{level}'})
        joined = gpd.sjoin(houses_gdf, layer, how='left', predicate='within')
        houses_gdf[f'assigned_{level}'] = joined[f'assigned_{level}']
        houses_gdf = houses_gdf.drop(columns=['index_right'])

    result = pd.DataFrame(houses_gdf.drop(columns=['geometry']))
    print('Completed school boundary assignment for houses.')
    return result


if __name__ == '__main__':
    convert_common_interest_points()
    if GEOPANDAS_AVAILABLE:
        print('geopandas is available. You can now use assign_school_boundaries_to_houses() with your housing dataset.')
    else:
        print('geopandas is not installed. To enable school boundary joins, install geopandas, shapely, and fiona.')
