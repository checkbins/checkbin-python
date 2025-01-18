import os, sys
import uuid
sys.path.insert(0, 'src')

import checkbin

company_id = "123"
question_id = "919"
short_uuid = str(uuid.uuid4())[:6]

checkbin.authenticate(token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2NvdW50SWQiOiJiN2VmODczOC0wNzRmLTRjYTgtYWM5Zi1hY2E1OTIwM2RiNDkiLCJpYXQiOjE3MzcxNzI2MDh9.dtbA42PyMT2jcTzUcXeEzcuPYvThV4C3tBVueaI2jfE")
checkbin_app = checkbin.App(app_key="testing_dedup", mode="remote")
bin_factory = checkbin_app.create_bin_factory(run_name=f"{company_id}_{question_id}_{short_uuid}")
checkbin = bin_factory.get_bin(input_state={"company_id": company_id, "question_id": question_id}, input_files={})

checkbin.checkin("test")
checkbin.add_state("generation", "this is a sample generation")
checkbin.submit()
