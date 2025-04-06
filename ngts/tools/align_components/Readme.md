## Component Alignment via Redfish

This script performs component alignment using the Redfish protocol and cpld update.

Description:
* Utilizes Redfish API for secure, standardized communication
* Supports alignment of Bmc, Erot, Fpga, Bios and CPLD
* Configurable path parameters for targeting specific components
* Easy integration with existing management tools

### Script actual location
After making new changes to this dir it should be copied to
  /auto/sw_system_project/NVOS_INFRA/verification_files/platform_components

cp -r ./align_components /auto/sw_system_project/NVOS_INFRA/verification_files/platform_components

### Usage
./python3 align_fw_components.py 

#### You need to provide parameters:
All flags are used as params (--setup_name=NVOS_juliet_10_7_148_136)
* setup_name - is REQUIRED to be able to get required information from noga.
* fw_versions_json_file - is used to find the path to the json file 
  * If this param doesn't exist and no component path provided => will default to juliet_versions.json
* erot_path, bmc_path, fpga_path, bios_path, pldm_path - providing path to install specified component, by providing any of this params the file will not be checked.
* bmc_user - User to connect to bmc (Optional, default is root)
* bmc_pass - Password to connect to bmc (Optional, default is root usual password)

### Flow
* Parses all required arguments.
* Gets required information from noga by setup_name.
* Verifies BMC_IP exists.
* Checks if component path is provided?
  * Yes → for each provided path for component perform update
  * No → perform update via fw_versions_json_file provided or default path '/auto/sw_system_project/NVOS_INFRA/verification_files/platform_components/juliet_versions.json'
* Compares installed against required version.
  * If they match → skip update
  * If they do not match → Update required component.
* Verify if any component was updated. 
  * If yes → perform power cycle
  * If no → skip power cycle
* Print installed component versions.

[Full guide](https://confluence.nvidia.com/pages/viewpage.action?spaceKey=SW&title=How+to+add+align+bmc+recipe+step+to+regression)

## File description
* align_cpld - entry point to script to update CPLD.
* align_fw_components - entry point to script to update components.
* Component - Abstract representation of a component to update.
* ComponentManager - Manager of components to perform updates, pc
* Constants - contains constants for names
* nogaq - Handles parsing from noga (Was copied from sonic-mgmt)
* Redfish_rest_api - Client to establish connection with RF
* rf_progress - different representation of task statuses of rf (Was copied from bmc scripts)

## Execution example output
Start component alignment script (/auto/sysgwork/aromashin/sonic-mgmt/ngts/tools/align_components/align_fw_components.py)  
Read platform components info from json /auto/sw_system_project/NVOS_INFRA/verification_files/platform_components/juliet_versions.json  
bmc is at version 88.0002.0927  
bios is at version 0ACTV_00.01.012  
erot is at version 01.04.0000.0000_n04  
fpga_encrypted is at version 0.1A  
No update required for bmc. Already at 88.0002.0927  
No update required for bios. Already at 0ACTV_00.01.012  
erot will be updated from 01.04.0000.0000_n04 to 01.04.0007.0000_n04  
Performing update for erot to 01.04.0007.0000_n04  
Task ID 0  
Start Time - 2025-01-28 14:49:03+00:00  
100.0% |██████████████████████████████████████████████████| The task with Id '0' has completed.  
End Time - 2025-01-28 14:49:09+00:00  
Total Time - 0:00:06  
Please proceed with AC power cycle  
No update required for fpga_encrypted. Already at 0.1A  
Power cycle request sent. Sleeping for 2.5 minutes...  
bmc is at version 88.0002.0927  
bios is at version 0ACTV_00.01.012  
erot is at version 01.04.0007.0000_n04  
fpga_encrypted is at version 0.1A  
Finished component alignment script (/auto/sysgwork/aromashin/sonic-mgmt/ngts/tools/align_components/align_fw_components.py)  


## License

SPDX-FileCopyrightText: Copyright (c) 2025
NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: LicenseRef-NvidiaProprietary

NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
property and proprietary rights in and to this material, related
documentation and any modifications thereto. Any use, reproduction,
disclosure or distribution of this material and related documentation
without an express license agreement from NVIDIA CORPORATION or
its affiliates is strictly prohibited.


## Contact

Aleksander Romashin - aromashin@nvidia.com
