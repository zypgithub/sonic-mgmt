# RC status — 202605_RC.70

- **RC branch:** `202605_RC`
- **Tag:** `202605_RC.70`
- **Upstream base:** `f6b6a7cb89440f428e2070a9daaacd6797071c19`
- **Summary:** 7 selected public operations — 4 applied, 3 reverted

| # | Kind | Module | Status | Source | Resolved SHA | Detail |
| ---: | --- | --- | --- | --- | --- | --- |
| 1 | APPLY | sonic-buildimage | APPLIED | https://github.com/sonic-net/sonic-buildimage/pull/28043 | `0f82320cf54337ed0016dca8826c93f843b036a2` | suppress full BGP route re-download when tcpdump toggles promiscuous mode |
| 2 | REVERT | sonic-buildimage | REVERTED | https://github.com/sonic-net/sonic-buildimage/pull/23978 | `e4318e5a7af2413caf2c606b68d4f83887c3ea50` | revert FEC configuration change |
| 3 | REVERT | sonic-buildimage | REVERTED | https://github.com/sonic-net/sonic-buildimage/pull/25357 | `109e38610c574d02b60fd84760e67b26b0b35bb2` | revert ACL YANG TCP_FLAGS constraint |
| 4 | APPLY | sonic-buildimage | APPLIED | https://github.com/sonic-net/sonic-buildimage/pull/26393 | `f621c65208cddaa1766f20d192d9b3ea8fa77dbd` | upgrade DHCP server container |
| 5 | REVERT | sonic-buildimage | REVERTED | https://github.com/sonic-net/sonic-buildimage/pull/28328 | `c8c517dc260a83a36093d51b2fd34eaf87d1725a` | revert container-side syslog rule handling from PR 26637 |
| 6 | APPLY | sonic-buildimage | APPLIED | https://github.com/sonic-net/sonic-buildimage/pull/26637 | `0a07161396f9da9c5c1c4bb3ff5df90db984010f` | reapply syslog rule ownership fix through PR 28328 |
| 7 | APPLY | sonic-buildimage | APPLIED | https://github.com/sonic-net/sonic-buildimage/pull/27682 | `dc21e64c28989133153b39d8ef94ee19eb7290d5` | fix service checker handling of process groups |

_Demo workaround assembled from the RC70 private commit range. It is not an official sonic-rc publication._
