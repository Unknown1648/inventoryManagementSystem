import dropbox
import time
import os
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

# Dropbox details
ACCESS_TOKEN = "sl.u.AFt_n68ezbhR0c2QrCkx8P4SrYRBYPZKiP7OfvUVwB1elz-aFI4sW4irPbyv9jjPiBT3f_cZTvB_AOdw65hyatnkqigtygvTGjbbj_YjsGrpOx1vu0RVn66SCaV3Vw4z8DEFe7hyBmiJhzHbt-Y4pdsWmrFNDbLQ0XciH-KUlZN2FZs7kQQjoizEHFTVQRHYi-DenVFvWYqNsglLnghvz47phe0QpcnhtW-U9CEsiNilbFjIl1zEgRF36MXN9_VoQmG6uzfKvhPci4TwrYZdF6UZeTYa_3zaal_CvGYvwDbvdxS57RVV_wsE4frr_Texlu4IWg872n5DTSRjKR9HcPrx1Cs9bVbhXOIaCEXeC4kKF_mQtaFkO0RTvvhEZ7eLiNR4Y0f3xLtP9OVCvDpFm_p45m37UEcGJz6ZaKZh6rvP12U5bGz9nHEfut7OYtltRNNBySF2rV8xh_bCyzuvt-dkw6e7zCyJG4jJEEm_MiJBMEc6IRBclFt13UmLXPOpd3KyFgu6gjW5DZasIFxMjPD1exVs37U8LbHCKTBn7N0WTZsoxyAutpAfUKQTY05zTTZlxbjwKdWa-blF_HMokZ4kF-Hk2FMWGnrUwmpYKI7VFNE9qkZm6p1a7gYKcAmx0zod_V2L2f3E1cOpJLUXnDxBuVDCqmveOKAOZ27543lGC7_bFcUBUh9vQcAoJVzY4iiX9ABByVeA3FZeoc6IPFDMqRv0X3a223gGhOSgal_-tPBhzYJbpae6bJP03GRhp-LSn7Q03yYXdjbOvNXkzD9nmbzS0hBtugbUVicskAHASL5NE01B_gl7QLWEubh-3LnDh2yup35wYMnNqhJ1YTTH6gAIDcEHMa8PqZyRlwr5k3xNoXs5QHhxIE4je5I6kl0R0PxaZ7Q_UYHn4xdxYODZCdJejdT4Ap4G_zsjipyRD0lgq93W7FZNtC91TB8lfCn5daTktfClBkv0FmWn3tb82AiqHE1Cg26HNIH2Sa2sFE8wXtkydU5aFLM3Kuf_XfiVVCQq7ahyqOyr2utIpRwmM4X-kcjhKYTbmnncFeErDl4yX3fNtGCTleBHeKToitxwzrCUgB_McQodO5e8iUp0ejuXA8ZggY-GFVgsFq2LUF-S0Cyk9KJGfBpp0TaHU7Z-CbmAXJ9j7E0R96J10Fn-jU0o5GHJU5fZbKiaK6xI7hIt-kpO3gb0XmSApd6S2Y1CB_X2vdrkR6wWANPMJ0RTFz2UoUQsLRvSWyXOf9RT53zVDqdBOkVGwVQ7377gC3H8ca_8trt5QIvYaAOumhFKwtUtb0Fgx56cOhXSM0FQZLYmE26EOL4_VTQur8vqhMSttxBApNjNBNjVSNJ15PCHUv9Aloke9qGeE8kWgtOD9Dx9ji2RPGPqnqNVG6IlUGQIHhnGBF0b3ex4IyPXHL5ajcR-vw7gV5dtPtG52f_pWA"
INVENTORY_DB_PATH = "inventory.db"
DROPBOX_BACKUP_PATH = "/backups/inventory_backup.db"

# initialize Dropbox client
dbx = dropbox.Dropbox(ACCESS_TOKEN)

def upload_file():
    """Upload inventory.db to Dropbox."""
    if not os.path.exists(INVENTORY_DB_PATH):
        print(f"Error: {INVENTORY_DB_PATH} not found.")
        return

    try:
        with open(INVENTORY_DB_PATH, "rb") as f:
            file_data = f.read()

        dbx.files_upload(file_data, DROPBOX_BACKUP_PATH, mode=dropbox.files.WriteMode.overwrite)
        print(f"Backup successful at {datetime.now()}")
    except Exception as e:
        print(f"Error uploading file: {e}")

def start_backup_scheduler(interval_seconds=3600):
    """Start background scheduler for auto backup."""
    scheduler = BackgroundScheduler()
    scheduler.add_job(upload_file, 'interval', seconds=interval_seconds)
    return scheduler