import uuid
from typing import Literal, Optional
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from tinydb import TinyDB, Query

app = FastAPI()
current_dir = Path(__file__).parent
db_dir = Path(current_dir, "client_db")
db_dir.mkdir(exist_ok=True)
db = TinyDB(db_dir / "db.json")


# Checkin
class CheckinFile(BaseModel):
    url: str
    mediaType: Optional[Literal["image", "video"]] = None
    pickle: Optional[bool] = None


class Checkin(BaseModel):
    name: Optional[str] = None
    state: Optional[dict] = None
    files: Optional[dict[str, CheckinFile]] = None


def create_checkin(
    checkin: Checkin,
    is_output: bool,
    run_id: Optional[str] = None,
    parent_id: Optional[str] = None,
):
    checkin_table = db.table("checkin")
    checkin_state_table = db.table("checkinState")
    new_checkin = {
        "id": str(uuid.uuid4()),
        "runId": run_id,
        "parentId": parent_id,
        "name": checkin.name,
        "isOutput": is_output,
        "createdAt": datetime.now().isoformat(),
        "updatedAt": datetime.now().isoformat(),
    }
    checkin_table.insert(new_checkin)
    state_list = []
    if checkin.state is not None:
        for key, value in checkin.state.items():
            state_list.append(
                {
                    "id": str(uuid.uuid4()),
                    "checkinId": new_checkin["id"],
                    "name": key,
                    "data": value,
                    "createdAt": datetime.now().isoformat(),
                    "updatedAt": datetime.now().isoformat(),
                }
            )
    if checkin.files is not None:
        for key, file in checkin.files.items():
            state = {
                "id": str(uuid.uuid4()),
                "checkinId": new_checkin["id"],
                "name": key,
                "createdAt": datetime.now().isoformat(),
                "updatedAt": datetime.now().isoformat(),
            }
            state.update(file)
            state_list.append(state)
    for state in state_list:
        checkin_state_table.insert(state)
    return new_checkin


def get_checkin_by_id(checkin_id: str, include_state: bool):
    checkin_table = db.table("checkin")
    checkin = checkin_table.search(Query().id == checkin_id)
    if len(checkin) == 0:
        raise HTTPException(
            status_code=404, detail=f"No checkin found with id {checkin_id}"
        )
    checkin = checkin[0].copy()
    if include_state:
        checkin_state_table = db.table("checkinState")
        state = checkin_state_table.search(Query().checkinId == checkin_id)
        checkin["state"] = state
    return checkin


@app.get("/checkin/{checkinId}")
def get_checkin(checkinId: str, includeState: bool = False):
    return get_checkin_by_id(checkinId, includeState)


class PostCheckins(BaseModel):
    runId: str
    checkins: list[Checkin]
    parentId: Optional[str] = None


@app.post("/checkin")
def create_checkins(body: PostCheckins):
    parent_id = body.parentId
    for index, checkin in enumerate(body.checkins):
        new_checkin = create_checkin(
            checkin, index == len(body.checkins) - 1, body.runId, parent_id
        )
        parent_id = new_checkin["id"]


# Set
@app.get("/set")
def get_sets():
    set_table = db.table("set")
    return set_table.all()


def get_set_by_id(
    set_id: str, include_checkins: bool = False, include_state: bool = False
):
    set_table = db.table("set")
    set = set_table.search(Query().id == set_id)
    if len(set) == 0:
        raise HTTPException(status_code=404, detail=f"No set found with id {set_id}")
    set = set[0].copy()
    if include_checkins:
        set_checkin_table = db.table("setCheckin")
        set_checkins = set_checkin_table.search(Query().setId == set_id)
        checkin_ids = [set_checkin["checkinId"] for set_checkin in set_checkins]
        checkin_table = db.table("checkin")
        checkins = checkin_table.search(Query().id.one_of(checkin_ids))
        checkins = [checkin.copy() for checkin in checkins]
        set["checkins"] = checkins
        if include_state:
            for checkin in checkins:
                checkin_state_table = db.table("checkinState")
                state = checkin_state_table.search(Query().checkinId == checkin["id"])
                checkin["state"] = state
    return set


@app.get("/set/{setId}")
def get_set(setId: str, includeCheckins: bool = False, includeState: bool = False):
    return get_set_by_id(setId, includeCheckins, includeState)


class PostSet(BaseModel):
    name: str
    isInput: bool
    checkins: list[Checkin]


def add_checkin_to_set(set_id: str, checkin_id: str):
    set_checkin_table = db.table("setCheckin")
    set_checkin_table.insert(
        {
            "setId": set_id,
            "checkinId": checkin_id,
            "createdAt": datetime.now().isoformat(),
            "updatedAt": datetime.now().isoformat(),
        }
    )


@app.post("/set")
def create_set(body: PostSet):
    set_table = db.table("set")
    set_id = str(uuid.uuid4())
    new_set = {
        "id": set_id,
        "name": body.name,
        "isInput": body.isInput,
        "createdAt": datetime.now().isoformat(),
        "updatedAt": datetime.now().isoformat(),
    }
    set_table.insert(new_set)
    for checkin in body.checkins:
        checkin.name = "Input"
        new_checkin = create_checkin(checkin, False)
        add_checkin_to_set(set_id, new_checkin["id"])
    return new_set


# Run
@app.get("/run")
def get_runs():
    run_table = db.table("run")
    return run_table.all()


def get_checkin_ancestors(checkins: list[dict], include_state: bool):
    checkin_table = db.table("checkin")
    tests = []
    for output_checkin in checkins:
        test = []
        current_checkin = output_checkin
        while current_checkin is not None:
            if include_state:
                checkin_state_table = db.table("checkinState")
                state = checkin_state_table.search(
                    Query().checkinId == current_checkin["id"]
                )
                current_checkin["state"] = state
            current_checkin.update(
                {
                    "createdAt": datetime.now().isoformat(),
                    "updatedAt": datetime.now().isoformat(),
                }
            )
            test.insert(0, current_checkin)
            parent_checkin = checkin_table.search(
                Query().id == current_checkin["parentId"]
            )
            if len(parent_checkin) == 0:
                current_checkin = None
            else:
                parent_checkin = parent_checkin[0].copy()
                current_checkin = parent_checkin
        tests.append(test)
    return tests


def get_run_by_id(
    run_id: str, include_checkins: bool = False, include_state: bool = False
):
    run_table = db.table("run")
    run = run_table.search(Query().id == run_id)
    if len(run) == 0:
        raise HTTPException(status_code=404, detail=f"No run found with id {run_id}")
    run = run[0].copy()
    if include_checkins:
        checkin_table = db.table("checkin")
        get_query = Query()
        checkins = checkin_table.search(
            get_query.runId == run_id and get_query.isOutput == True
        )
        checkins = [checkin.copy() for checkin in checkins]
        run["checkins"] = get_checkin_ancestors(checkins, include_state)
    return run


@app.get("/run/{runId}")
def get_run(runId: str, includeCheckins: bool = False, includeState: bool = False):
    return get_run_by_id(runId, includeCheckins, includeState)


def get_run_count():
    run_table = db.table("run")
    return len(run_table.all())


class PostRun(BaseModel):
    name: Optional[str] = None


@app.post("/run")
def create_run(body: PostRun):
    run_table = db.table("run")
    run_id = str(uuid.uuid4())
    name = body.name
    if name is None:
        name = f"Run {get_run_count() + 1}"
    new_run = {
        "id": run_id,
        "name": name,
        "createdAt": datetime.now().isoformat(),
        "updatedAt": datetime.now().isoformat(),
    }
    run_table.insert(new_run)
    return new_run


# Test
@app.get("/test")
def get_test(runId: str):
    test_table = db.table("test")
    return test_table.search(Query().runId == runId)


class Test(BaseModel):
    inputCheckinId: str
    status: Literal["pending", "running", "completed", "failed"] = "pending"


class PostTests(BaseModel):
    runId: str
    tests: list[Test]


@app.post("/test")
def create_tests(body: PostTests):
    test_table = db.table("test")
    for test in body.tests:
        test_table.insert(
            {
                "id": str(uuid.uuid4()),
                "runId": body.runId,
                "inputCheckinId": test.inputCheckinId,
                "status": test.status,
                "createdAt": datetime.now().isoformat(),
                "updatedAt": datetime.now().isoformat(),
            }
        )
    return test_table.search(Query().runId == body.runId)


class PatchTest(BaseModel):
    status: Literal["pending", "running", "completed", "failed"]


@app.patch("/test/{testId}")
def update_test(testId: str, body: PatchTest):
    test_table = db.table("test")
    ids = test_table.update(
        {
            "status": body.status,
            "updatedAt": datetime.now().isoformat(),
        },
        Query().id == testId,
    )
    if len(ids) == 0:
        raise HTTPException(status_code=404, detail=f"No test found with id {testId}")
    return test_table.get(doc_id=ids[0])
