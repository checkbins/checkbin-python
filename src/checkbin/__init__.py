# SPDX-FileCopyrightText: 2024-present Synth Inc
#
# SPDX-License-Identifier: MIT

import os
import csv
import time
import uuid
import json
import copy
import random
import pickle
import tempfile
import traceback
from pathlib import Path
from io import BufferedReader
from contextlib import contextmanager
from typing import Optional, Any, Tuple, Literal, Generator
from PIL import Image

import cv2
import numpy
import torch
import requests
import boto3
from tinydb import TinyDB, Query
from google.cloud import storage
from azure.storage.blob import BlobServiceClient
from azure.storage.filedatalake import DataLakeServiceClient

from .__about__ import __version__
from .utils import with_typehint

current_dir = Path(__file__).parent
db_dir = Path(current_dir, "cache")
db_dir.mkdir(exist_ok=True)
db = TinyDB(db_dir / "db.json")

MediaType = Literal["image", "video"]

CHECKBIN_REMOTE_URL = "https://api.checkbin.dev"

AUTH_TOKEN = None


def authenticate(token: str):
    global AUTH_TOKEN
    AUTH_TOKEN = token


def get_headers():
    if AUTH_TOKEN is not None:
        return {"Authorization": f"Bearer {AUTH_TOKEN}"}
    return {}


def handle_http_error(response: requests.Response):
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        content = json.loads(response.content)
        message = f"Checkbin API Error: status {response.status_code}, message: {content['message']}"
        raise Exception(message) from e


class FileUploader:
    def __init__(self, app_key: str, mode: Literal["local", "remote"]):
        self.app_key = app_key
        self.mode = mode
        self.azure_account_name = None
        self.azure_account_key = None
        self.aws_access_key = None
        self.aws_secret_key = None
        self.gcp_service_account_info = None
        self.gcp_service_account_json = None

    def add_azure_credentials(self, account_name: str, account_key: str):
        self.azure_account_name = account_name
        self.azure_account_key = account_key

    def add_aws_credentials(self, access_key: str, secret_key: str):
        self.aws_access_key = access_key
        self.aws_secret_key = secret_key

    def add_gcp_credentials_info(self, service_account_info: dict):
        self.gcp_service_account_info = service_account_info

    def add_gcp_credentials_json(self, service_account_json: str):
        self.gcp_service_account_json = service_account_json

    def check_credentials(
        self, storage_service: Optional[Literal["azure", "aws", "gcp"]] = None
    ):
        if storage_service == "azure":
            if self.azure_account_name is None:
                raise Exception("Azure account name is required")
            if self.azure_account_key is None:
                raise Exception("Azure account key is required")
        elif storage_service == "aws":
            if self.aws_access_key is None:
                raise Exception("AWS access key is required")
            if self.aws_secret_key is None:
                raise Exception("AWS secret key is required")
        elif storage_service == "gcp":
            if (
                self.gcp_service_account_info is None
                and self.gcp_service_account_json is None
            ):
                raise Exception("GCP service account info or json is required")

    def generate_filename(self, extension: str):
        return f"{uuid.uuid4()}{extension}"

    def upload_file_checkbin(
        self,
        extension: str,
        file: BufferedReader,
        run_id: Optional[str] = None,
        set_id: Optional[str] = None,
    ):
        if self.mode == "local":
            raise Exception("Checkbin file hosting is not available in local mode")

        filename = self.generate_filename(extension)

        file.seek(0, os.SEEK_END)
        size = file.tell()
        file.seek(0)

        file_response = requests.post(
            f"{CHECKBIN_REMOTE_URL}/file",
            headers=get_headers(),
            json={
                "appKey": self.app_key,
                "filename": filename,
                "size": size,
                "runId": run_id,
                "setId": set_id,
            },
            timeout=30,
        )
        handle_http_error(file_response)
        file_data = json.loads(file_response.content)
        sas_token = file_data["sasToken"]
        file_path = file_data["path"]

        service_client = DataLakeServiceClient(
            "https://checkbin.dfs.core.windows.net", credential=sas_token
        )
        file_system_client = service_client.get_file_system_client("user-storage")
        file_client = file_system_client.get_file_client(file_path)
        file_client.upload_data(file, overwrite=True)
        return f"https://checkbin.blob.core.windows.net/user-storage/{file_path}"

    def upload_file_azure(self, container: str, extension: str, file: BufferedReader):
        blob_service_client = BlobServiceClient(
            account_url=f"https://{self.azure_account_name}.blob.core.windows.net",
            credential=self.azure_account_key,
        )
        container_client = blob_service_client.get_container_client(container)
        filename = self.generate_filename(extension)
        blob_client = container_client.get_blob_client(filename)
        blob_client.upload_blob(file)
        return blob_client.url

    def upload_file_aws(self, bucket: str, extension: str, file: BufferedReader):
        s3_client = boto3.client(
            "s3",
            aws_access_key_id=self.aws_access_key,
            aws_secret_access_key=self.aws_secret_key,
        )
        filename = self.generate_filename(extension)
        s3_client.upload_fileobj(file, bucket, filename)
        return f"https://{bucket}.s3.amazonaws.com/{filename}"

    def upload_file_gcp(self, bucket: str, extension: str, file: BufferedReader):
        if self.gcp_service_account_info is not None:
            storage_client = storage.Client.from_service_account_info(
                self.gcp_service_account_info
            )
        else:
            storage_client = storage.Client.from_service_account_json(
                self.gcp_service_account_json
            )
        bucket_client = storage_client.get_bucket(bucket)
        filename = self.generate_filename(extension)
        blob_client = bucket_client.blob(filename)
        blob_client.upload_from_file(file)
        return f"https://storage.googleapis.com/{bucket}/{filename}"


class Checkin:
    def __init__(
        self,
        file_uploader: FileUploader,
        name: str,
        run_id: Optional[str] = None,
        set_id: Optional[str] = None,
    ):
        self.file_uploader = file_uploader
        self.name = name
        self.state_names = set()
        self.state = None
        self.evals = None
        self.files = None
        self.run_id = run_id
        self.set_id = set_id

    @classmethod
    def from_dict(cls, file_uploader: FileUploader, name: str, data: dict[str, Any]):
        checkin = cls(file_uploader, name)
        for key, value in data.items():
            if isinstance(value, str) and value.startswith("http"):
                basename = os.path.basename(value)
                _, extension = os.path.splitext(basename)
                extension = extension.lower()

                image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
                video_extensions = {".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm"}

                media_type = None
                if extension in image_extensions:
                    media_type = "image"
                elif extension in video_extensions:
                    media_type = "video"

                # Add file with determined media type
                checkin.add_file(key, value, media_type)
            else:
                checkin.add_state(key, value)
        return checkin

    def to_dict(self):
        return {
            "name": self.name,
            "state": self.state,
            "evals": self.evals,
            "files": self.files,
        }

    def __get_state_name(self, state_name: str) -> str:
        if state_name not in self.state_names:
            return state_name

        level = 1
        new_state_name = state_name
        while new_state_name in self.state_names:
            new_state_name = f"{state_name}_{level}"
            level += 1
        return new_state_name

    def add_state(self, name: str, state: Any):
        if self.state is None:
            self.state = {}
        name = self.__get_state_name(name)
        self.state[name] = state
        self.state_names.add(name)

    def add_eval(self, name: str, eval: int | float | bool):
        if not isinstance(eval, (int, float, bool)):
            print(f"Checkbin: WARNING unsupported eval type: {type(eval).__name__}")
        if self.evals is None:
            self.evals = {}
        name = self.__get_state_name(name)
        self.evals[name] = {
            "data": eval,
        }
        self.state_names.add(name)

    def add_file(
        self,
        name: str,
        url: str,
        media_type: Optional[MediaType] = None,
        pickle: bool = False,
    ):
        if self.files is None:
            self.files = {}
        name = self.__get_state_name(name)
        self.files[name] = {
            "url": url,
            "mediaType": media_type,
            "pickle": pickle,
        }
        self.state_names.add(name)

    def upload_file(
        self,
        name: str,
        file_path: str,
        media_type: Optional[MediaType] = None,
        pickle: bool = False,
        container: Optional[str] = None,
        storage_service: Optional[Literal["azure", "aws", "gcp"]] = None,
    ):
        self.file_uploader.check_credentials(storage_service)

        with open(file_path, "rb") as file:
            start_time = time.time()
            print(f"Checkbin: recording file")
            _, extension = os.path.splitext(os.path.basename(file_path))
            if storage_service == "azure":
                url = self.file_uploader.upload_file_azure(container, extension, file)
            elif storage_service == "aws":
                url = self.file_uploader.upload_file_aws(container, extension, file)
            elif storage_service == "gcp":
                url = self.file_uploader.upload_file_gcp(container, extension, file)
            else:
                url = self.file_uploader.upload_file_checkbin(
                    extension, file, self.run_id, self.set_id
                )
            print(f"Checkbin: recording file upload time: {time.time() - start_time}")
            print(f"Checkbin: recorded file: {url}")

        self.add_file(name, url, media_type, pickle)

    def upload_pickle(
        self,
        name: str,
        variable: Any,
        container: Optional[str] = None,
        storage_service: Optional[Literal["azure", "aws", "gcp"]] = None,
    ):
        self.file_uploader.check_credentials(storage_service)

        with tempfile.NamedTemporaryFile(suffix=".pkl") as tmp_file:
            pickle.dump(variable, tmp_file)
            self.upload_file(
                name=name,
                file_path=tmp_file.name,
                pickle=True,
                container=container,
                storage_service=storage_service,
            )

    def upload_image(
        self,
        name: str,
        image: Image,
        extension: str = ".jpg",
        container: Optional[str] = None,
        storage_service: Optional[Literal["azure", "aws", "gcp"]] = None,
    ):
        with tempfile.NamedTemporaryFile(suffix=extension) as tmp_file:
            image.save(tmp_file.name)
            self.upload_file(
                name,
                tmp_file.name,
                media_type="image",
                container=container,
                storage_service=storage_service,
            )

    def __colorspace_to_conversion(self, colorspace: str) -> Optional[int]:
        if colorspace == "BGRA":
            return cv2.COLOR_BGRA2BGR
        elif colorspace == "RGBA":
            return cv2.COLOR_RGBA2BGR
        elif colorspace == "RGB":
            return cv2.COLOR_RGB2BGR
        elif colorspace == "GRAY":
            return cv2.COLOR_GRAY2BGR
        elif colorspace == "YCrCb":
            return cv2.COLOR_YCrCb2BGR
        elif colorspace == "HSV":
            return cv2.COLOR_HSV2BGR
        elif colorspace == "Lab":
            return cv2.COLOR_Lab2BGR
        elif colorspace == "Luv":
            return cv2.COLOR_Luv2BGR
        elif colorspace == "HLS":
            return cv2.COLOR_HLS2BGR
        elif colorspace == "YUV":
            return cv2.COLOR_YUV2BGR
        else:
            return None

    def upload_array_as_image(
        self,
        name: str,
        array: numpy.ndarray | torch.Tensor,
        range: Tuple[int, int] = (0, 255),
        colorspace: Optional[
            Literal[
                "BGR",
                "BGRA",
                "RGBA",
                "RGB",
                "GRAY",
                "YCrCb",
                "HSV",
                "Lab",
                "Luv",
                "HLS",
                "YUV",
            ]
        ] = None,
        container: Optional[str] = None,
        storage_service: Optional[Literal["azure", "aws", "gcp"]] = None,
    ):
        self.file_uploader.check_credentials(storage_service)

        if isinstance(array, torch.Tensor):
            array = array.detach().cpu().numpy()

        min_val, max_val = range
        array = array.astype(float)  # Cast to float to avoid overflow
        array = ((array - min_val) * 255) / (max_val - min_val)

        if (
            colorspace is not None
            and self.__colorspace_to_conversion(colorspace) is not None
        ):
            array = cv2.cvtColor(array, self.__colorspace_to_conversion(colorspace))

        with tempfile.NamedTemporaryFile(suffix=".jpg") as tmp_file:
            cv2.imwrite(tmp_file.name, array)
            self.upload_file(
                name=name,
                file_path=tmp_file.name,
                media_type="image",
                container=container,
                storage_service=storage_service,
            )


class Bin(with_typehint(Checkin)):
    def __init__(
        self,
        trace_id: str,
        run_id: str,
        parent_id: str,
        base_url: str,
        file_uploader: FileUploader,
        state: Optional[dict[str, Any]] = None,
    ):
        self.trace_id = trace_id
        self.run_id = run_id
        self.parent_id = parent_id
        self.base_url = base_url
        self.file_uploader = file_uploader
        self.state = state
        self.input_state_fetched = False
        self.input_state = None
        self.checkins: list[Checkin] = []
        self.is_running = False

    def get_data(self, name: str) -> Optional[Any]:
        if self.state is None or name not in self.state:
            return None
        return self.state[name]["data"]

    def get_file_url(self, name: str) -> Optional[str]:
        if self.state is None or name not in self.state:
            return None
        return self.state[name]["url"]

    def get_file(self, name: str) -> Optional[dict[str, Any]]:
        if self.state is None or name not in self.state:
            return None
        return {
            "url": self.state[name]["url"],
            "media_type": self.state[name]["mediaType"],
            "pickle": self.state[name]["pickle"],
        }

    def get_input_state(self):
        checkin_input_response = requests.get(
            f"{self.base_url}/checkin/{self.parent_id}/input",
            headers=get_headers(),
            params={"includeState": "true"},
            timeout=30,
        )
        handle_http_error(checkin_input_response)
        checkin = json.loads(checkin_input_response.content)
        self.input_state_fetched = True
        self.input_state = {state["name"]: state for state in checkin["state"]}

    def get_input_data(self, name: str) -> Optional[Any]:
        if not self.input_state_fetched:
            self.get_input_state()
        if self.input_state is None or name not in self.input_state:
            return None
        return self.input_state[name]["data"]

    def get_input_file_url(self, name: str) -> Optional[str]:
        if not self.input_state_fetched:
            self.get_input_state()
        if self.input_state is None or name not in self.input_state:
            return None
        return self.input_state[name]["url"]

    def get_input_file(self, name: str) -> Optional[dict[str, Any]]:
        if not self.input_state_fetched:
            self.get_input_state()
        if self.input_state is None or name not in self.input_state:
            return None
        return {
            "url": self.input_state[name]["url"],
            "media_type": self.input_state[name]["mediaType"],
            "pickle": self.input_state[name]["pickle"],
        }

    def checkin(
        self,
        name: str,
    ):
        self.checkins.append(Checkin(self.file_uploader, name, self.run_id))

        if not self.is_running:
            trace_response = requests.patch(
                f"{self.base_url}/trace/{self.trace_id}",
                headers=get_headers(),
                json={"status": "running"},
                timeout=30,
            )
            handle_http_error(trace_response)
            self.is_running = True

    def submit(self):
        create_response = requests.post(
            f"{self.base_url}/checkin",
            headers=get_headers(),
            json={
                "runId": self.run_id,
                "parentId": self.parent_id,
                "checkins": [checkin.to_dict() for checkin in self.checkins],
            },
            timeout=30,
        )
        handle_http_error(create_response)

        trace_response = requests.patch(
            f"{self.base_url}/trace/{self.trace_id}",
            headers=get_headers(),
            json={"status": "completed"},
            timeout=30,
        )
        handle_http_error(trace_response)

    def failure(self, error_name: str, error_message: str, error_stack: str):
        trace_response = requests.patch(
            f"{self.base_url}/trace/{self.trace_id}",
            headers=get_headers(),
            json={
                "status": "failed",
                "errorName": error_name,
                "errorMessage": error_message,
                "errorStack": error_stack,
            },
            timeout=30,
        )
        handle_http_error(trace_response)

    def __getattr__(self, name):
        if len(self.checkins) == 0:
            raise AttributeError(
                f"'Bin' object has no attribute '{name}'. Create at least one checkin."
            )
        return getattr(self.checkins[-1], name)


class Checkbin:
    def __init__(self, bins: list[Bin]):
        self.length = len(bins)
        self.bins = iter(bins)
        self.current_bin = None

    def __len__(self):
        return self.length

    def __iter__(self):
        return self

    def __next__(self):
        self.current_bin = next(self.bins)
        return self.current_bin


class InputSet:
    def __init__(
        self,
        app_key: str,
        base_url: str,
        file_uploader: FileUploader,
        name: str,
    ):
        self.app_key = app_key
        self.base_url = base_url
        self.file_uploader = file_uploader
        self.name = name
        self.checkins: list[Checkin] = []
        set_response = requests.post(
            f"{self.base_url}/set",
            headers=get_headers(),
            json={
                "appKey": self.app_key,
                "name": self.name,
                "isInput": True,
            },
            timeout=30,
        )
        handle_http_error(set_response)
        set_data = json.loads(set_response.content)
        self.set_id = set_data["id"]

    def add_input(self):
        checkin = Checkin(self.file_uploader, "Input")
        self.checkins.append(checkin)
        return checkin

    @classmethod
    def get_file_set_id(cls, file_path: str) -> Optional[str]:
        file_table = db.table("file")
        query_result = file_table.search(Query().path == file_path)
        if len(query_result) > 0:
            file_stats = os.stat(file_path)
            existing_file = query_result[0]
            if (
                existing_file["size"] == file_stats.st_size
                and existing_file["last_modified"] == file_stats.st_mtime
            ):
                return existing_file["set_id"]
        return None

    @classmethod
    def cache_file_set_id(cls, file_path: str, set_id: str):
        file_table = db.table("file")
        file_stats = os.stat(file_path)
        file_data = {
            "path": file_path,
            "size": file_stats.st_size,
            "last_modified": file_stats.st_mtime,
            "set_id": set_id,
        }

        query_result = file_table.search(Query().path == file_path)
        if len(query_result) > 0:
            file_table.update(file_data, Query().path == file_path)
        else:
            file_table.insert(file_data)

    def create_from_json(
        self,
        json_data: Optional[list[dict[str, Any]]] = None,
        json_file: Optional[str] = None,
    ):
        json_dict = json_data

        if json_file is not None:
            with open(json_file, "r") as file:
                json_dict = json.load(file)

        if json_dict is None:
            raise Exception("Either json_data or json_file must be provided")

        if not isinstance(json_dict, list):
            raise Exception("JSON must be a list")

        for item in json_dict:
            if not isinstance(item, dict):
                raise Exception("Each element in the JSON list must be a dictionary")

        self.checkins = [
            Checkin.from_dict(self.file_uploader, "Input", data) for data in json_dict
        ]

        return self.submit()

    def create_from_csv(self, csv_file: str):
        with open(csv_file, "r") as file:
            csv_reader = csv.DictReader(file)

            self.checkins = [
                Checkin.from_dict(self.file_uploader, "Input", row)
                for row in csv_reader
            ]

        return self.submit()

    def submit(self):
        set_response = requests.patch(
            f"{self.base_url}/set/{self.set_id}/checkin",
            headers=get_headers(),
            json={
                "checkins": [checkin.to_dict() for checkin in self.checkins],
            },
            timeout=30,
        )
        handle_http_error(set_response)
        self.checkins = []
        return self.set_id


class App:
    def __init__(
        self,
        app_key: str,
        mode: Literal["local", "remote"] = "remote",
        port: int = 8000,
    ):
        self.app_key = app_key
        self.package_status_message = None
        if mode == "local":
            self.base_url = f"http://localhost:{port}"
        else:
            self.base_url = CHECKBIN_REMOTE_URL
            package_response = requests.get(
                f"{self.base_url}/public/package/status",
                headers=get_headers(),
                params={"manager": "pip", "name": "checkbin", "version": __version__},
                timeout=30,
            )
            handle_http_error(package_response)
            package_data = json.loads(package_response.content)
            if "message" in package_data:
                self.package_status_message = package_data["message"]

        self.file_uploader = FileUploader(app_key=app_key, mode=mode)

    def add_azure_credentials(self, account_name: str, account_key: str):
        self.file_uploader.add_azure_credentials(
            account_name=account_name, account_key=account_key
        )

    def add_aws_credentials(self, access_key: str, secret_key: str):
        self.file_uploader.add_aws_credentials(
            access_key=access_key, secret_key=secret_key
        )

    def add_gcp_credentials_info(self, service_account_info: dict):
        self.file_uploader.add_gcp_credentials_info(
            service_account_info=service_account_info
        )

    def add_gcp_credentials_json(self, service_account_json: str):
        self.file_uploader.add_gcp_credentials_json(
            service_account_json=service_account_json
        )

    def create_input_set(self, name: str) -> InputSet:
        if self.package_status_message is not None:
            print(self.package_status_message)

        return InputSet(
            app_key=self.app_key,
            base_url=self.base_url,
            file_uploader=self.file_uploader,
            name=name,
        )

    @contextmanager
    def start_run(
        self,
        name: Optional[str] = None,
        checkin_id: Optional[str] = None,
        set_id: Optional[str] = None,
        run_id: Optional[str] = None,
        json_file: Optional[str] = None,
        csv_file: Optional[str] = None,
        sample_size: Optional[int] = None,
        duplicate_factor: Optional[int] = None,
    ) -> Generator[Checkbin, None, None]:
        if self.package_status_message is not None:
            print(self.package_status_message)

        run_response = requests.post(
            f"{self.base_url}/run",
            headers=get_headers(),
            json={"appKey": self.app_key, "name": name},
            timeout=30,
        )
        handle_http_error(run_response)
        run_data = json.loads(run_response.content)
        run_id = run_data["id"]

        input_set = None
        if json_file is not None:
            set_id = InputSet.get_file_set_id(json_file)
            if set_id is None:
                input_set = self.create_input_set(os.path.basename(json_file))
                set_id = input_set.create_from_json(json_file=json_file)
                InputSet.cache_file_set_id(json_file, set_id)
        elif csv_file is not None:
            set_id = InputSet.get_file_set_id(csv_file)
            if set_id is None:
                input_set = self.create_input_set(os.path.basename(csv_file))
                set_id = input_set.create_from_csv(csv_file=csv_file)
                InputSet.cache_file_set_id(csv_file, set_id)

        checkins = []
        if checkin_id is not None:
            checkin_response = requests.get(
                f"{self.base_url}/checkin/{checkin_id}",
                headers=get_headers(),
                params={"includeState": "true"},
                timeout=30,
            )
            handle_http_error(checkin_response)
            checkin = json.loads(checkin_response.content)
            checkins = [checkin]
        elif set_id is not None:
            set_response = requests.get(
                f"{self.base_url}/set/{set_id}",
                headers=get_headers(),
                params={"includeCheckins": "true", "includeState": "true"},
                timeout=30,
            )
            handle_http_error(set_response)
            set = json.loads(set_response.content)
            checkins = set["checkins"]
        elif run_id is not None:
            run_inputs_response = requests.get(
                f"{self.base_url}/run/{run_id}/input",
                headers=get_headers(),
                params={"includeState": "true"},
                timeout=30,
            )
            handle_http_error(run_inputs_response)
            checkins = json.loads(run_inputs_response.content)
        else:
            raise Exception("Either checkin_id or set_id or run_id must be provided")

        if len(checkins) > 1 and sample_size is not None:
            checkins = random.sample(checkins, min(sample_size, len(checkins)))

        checkins_dict = {checkin["id"]: checkin for checkin in checkins}

        if duplicate_factor is not None:
            checkins = [
                copy.deepcopy(checkin)
                for _ in range(duplicate_factor)
                for checkin in checkins
            ]

        traces_response = requests.post(
            f"{self.base_url}/trace",
            headers=get_headers(),
            json={
                "runId": run_id,
                "traces": [{"inputCheckinId": checkin["id"]} for checkin in checkins],
            },
            timeout=30,
        )
        handle_http_error(traces_response)
        traces = json.loads(traces_response.content)

        print(f"Checkbin: started run {run_id} with {len(traces)} traces")

        bins = []
        for trace in traces:
            bin = Bin(
                trace_id=trace["id"],
                run_id=run_id,
                parent_id=trace["inputCheckinId"],
                base_url=self.base_url,
                file_uploader=self.file_uploader,
                state={
                    state["name"]: state
                    for state in checkins_dict[trace["inputCheckinId"]]["state"]
                },
            )
            bins.append(bin)

        checkbin = Checkbin(bins)
        try:
            yield checkbin
        except Exception as e:
            if checkbin.current_bin is not None:
                error_stack = None
                if hasattr(e, "__traceback__"):
                    error_stack = "".join(traceback.format_tb(e.__traceback__))
                checkbin.current_bin.failure(
                    error_name=type(e).__name__,
                    error_message=str(e),
                    error_stack=error_stack,
                )
            raise e
