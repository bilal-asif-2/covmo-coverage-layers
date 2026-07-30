import os
import tempfile
import geopandas as gpd
import pandas_gbq
from shapely import wkt
from google.cloud import storage, bigquery

BUCKET_NAME = os.getenv("BUCKET_NAME", "srpq-covmo-plots")
START_DATE = os.getenv("START_DATE", "2026-06-01")
PROJECT_ID = os.getenv("PROJECT_ID", "optus-anpq-cdw-prd")
DATASET = os.getenv("DATASET", "USER_bilal_asif")
TABLE = os.getenv("TABLE", "covmo_coverage_tiles")

STATES = os.getenv("STATES", "VIC,TAS,ACT,NSW,NT,QLD,SA,WA").split(",")
TECHS = os.getenv("TECHS", "4G,5G-NSA").split(",")

gcs_client = storage.Client()
bq_client = bigquery.Client()


def build_tiles():
    query = f"""
    CREATE OR REPLACE TABLE `{PROJECT_ID}.{DATASET}.{TABLE}` AS (
      WITH raw_covmo AS (
        SELECT
          REGEXP_EXTRACT(cell_name, r':([^:-]+)-') AS site,
          tech,
          band,
          qb_19,
          mr_sum,
          avg_rsrp
        FROM `{PROJECT_ID}.ANSPQ_CovMo.work_locations_PUB_T`
        WHERE start_of_week_date >= "{START_DATE}"
      ),
      nw_config AS (
        SELECT DISTINCT SITE_ID, STATE
        FROM `{PROJECT_ID}.srpq_stats.mnis_raw_v`
      )
      SELECT
        STATE,
        qb_19,
        tech,
        band,
        ST_ASTEXT(carto.QUADBIN_BOUNDARY(qb_19)) AS wkt_polygon,
        SUM(mr_sum * avg_rsrp) / SUM(mr_sum) AS avg_rsrp,
        SUM(mr_sum) AS total_mr
      FROM raw_covmo a
      JOIN nw_config b ON a.site = b.SITE_ID
      GROUP BY 1,2,3,4
    )
    """
    bq_client.query(query).result()
    print("Built coverage tile table")


def export_layers():
    bucket = gcs_client.bucket(BUCKET_NAME)

    for state in STATES:
        for tech in TECHS:
            bands = ["700", "1800"] if tech == "4G" else ["2300", "3500"]

            for band in bands:
                sql = f"""
                SELECT
                  qb_19,
                  STATE,
                  tech,
                  band,
                  wkt_polygon,
                  SAFE_CAST(avg_rsrp AS FLOAT64) AS avg_rsrp,
                  SAFE_CAST(total_mr AS FLOAT64) AS total_mr
                FROM `{PROJECT_ID}.{DATASET}.{TABLE}`
                WHERE STATE = "{state}" AND tech = "{tech}" AND band = "{band}"
                """

                df = pandas_gbq.read_gbq(sql, project_id=PROJECT_ID)
                if df.empty:
                    print(f"Skipping empty result: {state} {tech} {band}")
                    continue

                df["geometry"] = df["wkt_polygon"].apply(wkt.loads)
                gdf = gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:4326")

                filename = f"CovMO_rsrp_tiles_{state}_{tech}_{band}.gpkg"
                layername = f"CovMO_rsrp_tiles_{state}_{tech}_{band}"

                with tempfile.TemporaryDirectory() as tmpdir:
                    local_path = os.path.join(tmpdir, filename)
                    gdf.to_file(local_path, layer=layername, driver="GPKG")

                    blob = bucket.blob(f"coverage-layers/{filename}")
                    blob.upload_from_filename(local_path)

                print(f"Uploaded {filename}")


if __name__ == "__main__":
    build_tiles()
    export_layers()
    print("Done")
    #test