import json
import urllib.parse

import requests

# Suppress the warning for insecure requests
requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)


class RedFishHTTPStatusCode:
    OK = 200
    Created = 201
    Accepted = 202
    No_Content = 204
    Moved_Permanently = 301
    Found = 302
    Not_Modified = 304
    Bad_Request = 400
    Unauthorized = 401
    Forbidden = 403
    Not_Found = 404
    Method_Not_Allowed = 405
    Not_Acceptable = 406
    Conflict = 409
    Gone = 410
    Length_Required = 411
    Precondition_Failed = 412
    Unsupported_Media_Type = 415
    Precondition_Required = 428
    Request_Header_Field_Too_Large = 431
    Internal_Server_Error = 500
    Not_Implemented = 501
    Service_Unavailable = 503
    Insufficient_Storage = 507


class RedFishRestApi:
    def __init__(self, ip, user, password):
        self.ip = ip
        self.username = user
        self.password = password

    def _gen_url(self, endpoint):
        url = urllib.parse.urljoin(f"https://{self.ip}", endpoint)
        return url

    def get_query(self, endpoint):
        """
        Perform a GET request to the specified URL with basic authentication.

        :param endpoint: The URL to send the GET request to.
        :return: The response data if the request is successful, otherwise an error message.
        """
        url = self._gen_url(endpoint)
        try:
            response = requests.get(url, auth=(self.username, self.password), verify=False)
        except Exception:
            raise

        if response.status_code <= RedFishHTTPStatusCode.Accepted:
            return response.json()
        else:
            raise Exception(f"Request failed with status code: {response.status_code}, Response text: {response.text}")

    def get_data_query(self, endpoint, file_path):
        """
        Perform a GET request to the specified URL with basic authentication.

        :param endpoint: The URL to send the GET request to.
        :param file_path: The path to the file to be downloaded.
        :return: The response data if the request is successful, otherwise an error message.
        """
        url = self._gen_url(endpoint)
        try:
            response = requests.get(url, auth=(self.username, self.password), verify=False, stream=True)
        except Exception:
            raise

        if response.status_code <= RedFishHTTPStatusCode.Accepted:
            with open(file_path, 'wb') as file:
                for chunk in response.iter_content(chunk_size=8192):
                    file.write(chunk)
            file.close()
        else:
            raise Exception(f"Request failed with status code: {response.status_code}, Response text: {response.text}")

    def post_query(self, endpoint, data=""):
        url = self._gen_url(endpoint)
        headers = {'Content-Type': 'application/json'}
        try:
            if data:
                response = requests.post(url, auth=(self.username, self.password), headers=headers,
                                         data=json.dumps(data), verify=False)
            else:
                response = requests.post(url, auth=(self.username, self.password), headers=headers, verify=False)
        except Exception:
            raise

        if response.status_code <= RedFishHTTPStatusCode.No_Content:
            return (response.json(), response.headers) if response.content else (None, None)
        else:
            raise Exception(f"Request failed with status code: {response.status_code}, Response text: {response.text}")

    def post_data_query(self, endpoint, file_path):
        """
        Perform a POST request to upload a file to the specified URL with basic authentication.

        :param endpoint: The URL to send the POST request to.
        :param file_path: The path to the file to be uploaded.
        :return: The response data if the upload is successful, otherwise an error message.
        """
        url = self._gen_url(endpoint)
        headers = {"Content-Type": "application/octet-stream"}
        with open(file_path, 'rb') as file:
            try:
                response = requests.post(url, auth=(self.username, self.password), headers=headers, data=file,
                                         verify=False)
            except Exception:
                file.close()
                raise

            if response.status_code <= RedFishHTTPStatusCode.Accepted:
                return response.json()
            else:
                raise Exception(
                    f"File upload failed with status code: {response.status_code}, Response text: {response.text}")
        file.close()

    def patch_query(self, endpoint, data, header=None):
        """
        Perform a PATCH request with a JSON payload to the specified URL with basic authentication.

        :param header: headers to append to the query
        :param endpoint: The URL to send the PATCH request to.
        :param data: The JSON payload to be sent in the PATCH request.
        :return: The response data if the request is successful, otherwise an error message.
        """
        if header is None:
            header = {}
        url = self._gen_url(endpoint)
        headers = {'Content-Type': 'application/json'}
        headers = headers.update(header)
        try:
            response = requests.patch(url, auth=(self.username, self.password), headers=headers, data=json.dumps(data),
                                      verify=False)
        except Exception:
            raise

        if response.status_code <= RedFishHTTPStatusCode.Accepted:
            return response.json() if response.content else None
        else:
            raise Exception(f"Request failed with status code: {response.status_code}, Response text: {response.text}")
