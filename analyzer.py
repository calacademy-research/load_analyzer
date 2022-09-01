#!/usr/bin/env python3
import db_utils

db = db_utils.DbUtils('root', 'qhALiqwRFNlOzwqnbXgGbKpgCZXUiSZvmAsRLlFIIMqjSQrf', 3312, 'ibss-central', 'load')
result = db.get_records("select * from processes")
print(f"records: {len(result)}")
