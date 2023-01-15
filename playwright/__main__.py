# Copyright (c) Microsoft Corporation.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import subprocess
import sys

from playwright._impl._driver import compute_driver_executable, get_driver_env


def main(*args) -> None:
    if len(args) == 0:
        args = sys.argv[1:]
    driver_executable = compute_driver_executable()
    completed_process = subprocess.run(
        [str(driver_executable), *args], env=get_driver_env()
    )
    sys.exit(completed_process.returncode)


if __name__ == "__main__":
    main()
