# LeRoy Override Requests

| Author | What was updated | Date |
| :---- | :---- | :---- |
| Anirudh Sabnis Email: ansabni@akamai.com | Draft created | 2025-06-04 |

This document describes the overrides provisioned in LeRoy. Each override request can be specified as a record in the [override.toml](https://git.source.akamai.com/projects/NETOPT/repos/leroy_config/browse/override/override.toml) file. An override record consists of:

**Override directive**: A certain rule associated with the override request. For example, Access-Control is an override directive that can be set to either “must-include”, “must-exclude”, or “allowed”. This allows us to specify the access-control associated with a maprule. The list of override directives are in the Table 2 below. 

**Geographical scope**: Defines the geographical scope on which the specified override is applied. It could be one of the following: default (all large regions), geo, country, metro, and the region itself. The list of geographical-scopes are in Table 1 below.

**Mapnames**: A list of maprules for which the override request is specified.

**Start-time**: Leroy accepts time specified in unix time. If provided, LeRoy will apply the override if the current time is greater than the Start-time. 

**End-time**: Leroy accepts time specified in unix time. If provided, LeRoy will apply the override if the current time is lesser than the Start-time. 

###  Rules for override requests

* Must contain only one override directive.

* Must contain only one geographical scope directive. For example, you should not provide Region-country and Region-number in the same override request

* Must contain only one Mapnames directive.

An override request will be rejected if it violates any of the above rules. 

**Specifying multiple values in Override-directive, Geographical scope, Mapnames.** One can specify multiple values in each geographical scope, override-directive, or Mapname as a list of values. For example, consider the following override request,

```
Ticket-id = "NETOPT-431"
Start-time = 1738325567
End-time = 1738325900
Region-number = [49440, 50565]
Mapnames = ["w25", "us"]
Quota-tb = [40, 80]
```

Here, the maps “w25” and “us” need a disk quota of 40TB and 80TB, respectively, in large regions 49440 and 50565\. Please note that the value indexed at the ith position in the override directive (Region-number \= \[49440, 50565\]), will be applied to the map indexed at the ith position in the Mapnames list (Mapnames \= \[“w25”, “us”\]). Further, the overrides will be applied to all the geos specified in the geographical scope directive. 

If a single override directive value applies to all the maps in the override request, the override directive can be specified as a single value and not a list. For example,

```
Ticket-id = "NETOPT-431"
Start-time = 1738325567
End-time = 1738325900
Region-number = [49440, 50565]
Mapnames = ["w25", "us"]
Access-control = "must-exclude"
```

Here, the “must-exclude” override directive is applied to both the maps “w25” and “us”. Thus, the override request asks LeRoy to exclude these two maps from regions 49440 and 50565\.

Table 1\. List of Geographical-Scopes

| Geographical Scope | Description |
| :---- | :---- |
| Region-number | Specify the region number(s) for the override request.  |
| Region-metro | Specify the metro for the override request. The list of metro\_areas can be found in netopt.netopt\_metro\_hierarchy in netarch |
| Region-country | Specify the country/countries for the override request. The country codes are available on Netarch using the below query: select country from CMN\_INT.AK\_GEOCODE |
| Region-geo | Specify the geo(s) for the override request. It could be one of the following: NA, LA, APAC, EMEA |
| Region-default | Applies to all large regions in the network. The requester must use the value “default” while specifying this override. |

Table 2\. List of Override-Directives

| Override Directive | Accepted Values | Functionality | Example |
| :---- | :---- | :---- | :---- |
| Access-control | “must-include”, “must-exclude”, “allowed” | Specifies the access-control of maprules for all large regions within the specified geographical-scope.  Include: forces leroy to include the maprules. Exclude: forces leroy to exclude the maprules Allowed: consider these maprules for allocation in the large regions | `## Include maprules us, mm1 to be served in the US Ticket-id = "NETOPT-431" Start-time = 1738325567 End-time = 1738325900 Region-country = ["US"] Mapnames = [“us”, “mm1”] Access-control = “must-exclude”` |
| Quota-multiplier | Any positive real number | Multiply the disk requirement of the maprule/maprules by the specified multiplier.  | `## Multiply the quotas for maprule w25 by 2 in region 49440 Ticket-id = "NETOPT-431" Start-time = 1738325567 End-time = 1738325900 Region-number = [49440] Mapnames = [“w25”] Quota-Multiplier = 2` |
| Traffic-multiplier | Any positive real number | Multiply the traffic of the maprule or a list of maprules by the specified multiplier. If a list of multipliers is specified, each number in the list corresponds to the equivalently indexed maprule in the  | `## Multiply the demand for maprules “us”, “mm1” by 2 in geo NA Ticket-id = "NETOPT-431" Start-time = 1738325567 End-time = 1738325900 Region-Geo = [“NA”] Maprule-names = [“us”, “mm1”] Traffic-multiplier = 2` |
| Quota-tb | Any positive real number | Specifies the quota in TB for a maprule or a list of maprules | `## Set the disk quotas of maprules w25 and mm1 to 40TB and 80TB resp., in region 49440. Ticket-id = "NETOPT-431" Start-time = 1738325567 End-time = 1738325900 Region-number = [49440] Mapnames = [2925, 19] Quota-tb = [40, 80]` |
| Traffic-gbps | Any positive real number | Specify traffic demand (in gbps) for the specified maprules. All large regions within the geographical scope will use the specified traffic demands. | `## Set the traffic demand values of maprules w25 and mm1 to 40gbps and 80gbps resp., for all LRs in the US. Ticket-id = "NETOPT-431" Start-time = 1738325567 End-time = 1738325900 Region-country = [“US”] Mapnames = [“us”, “mm1”] Demand_Gbps = [40, 80]` |
| Quota-pct | Any real number between 1 and 92\. Because we do not want to allocate more than 92% of the large region’s capacity. | Specify the quota as a percentage of the large region’s disk space. | `## Set the quota percentages of maprules mch-ff-lo and mch-ff-so to 5% and 1%, respectively in all large regions  Ticket-id = "NETOPT-431" Start-time = 1738325567 End-time = 1738325900 Region-default = [“default”]  Mapnames = [“mch-ff-lo”, “mch-ff-so”] Quota-pct = [5, 1]` |
| Object-count-quota-pct | Any positive real number between 0 and 100 | Specify the object count percentage for the maprule | `Ticket-id = "NETOPT-431" Start-time = 1738325567 End-time = 1738325900 Region-default = [“default”]  Mapnames = [“mch-ff-lo”, “mch-ff-so”]  Object-count-quota-pct = [5, 1]`  |
| BLC-only | Boolean: true or false | If a map has to be added only to BLC and not FCS | `Ticket-id = "NETOPT-431" Start-time = 1738325567 End-time = 1738325900 Region-default = [“default”]  Mapnames = [“t”, “api-105”]  BLC-only=true`  |
| FCS-only | Boolean: true or false | If a map has to be added only to FCS and not to BLC | `Ticket-id = "NETOPT-431" Start-time = 1738325567 End-time = 1738325900 Region-default = [“default”]  Mapnames = [“v”] FCS-only=true`  |
| LR-available-servers | A positive integer | The number of servers available in the LR by the specified number. If maprule-ids are specified in the override request, they will be ignored. The geographical scope for this request must be region-number. | `## Set the number of servers in the large region to 65 Ticket-id = "NETOPT-431" Start-time = 1738325567 End-time = 1738325900 Region_number = [49440] LR-available-servers=65` |
| LR-available-server-multiplier | A positive real number | Multiply the disk available in the LR by the specified multiplier. If maprule-ids are specified in the override request, they will be ignored. The geographical scope for this request must be region-number | `## Multiply the disk in the large region by the multiplier Ticket-id = "NETOPT-431" Start-time = 1738325567 End-time = 1738325900 Region_number = [49440] LR-available-server-multiplier=2` |
| LR-disk-capacity-tb | A positive real number | Set the disk space available in the LR by the specified number. If maprule-ids are specified in the override request, they will be ignored. The geographical scope for this request must be region-number. | `## Set the disk available in the large region to 1065TB Ticket-id = "NETOPT-431" Start-time = 1738325567 End-time = 1738325900 Region_number = [49440] LR-disk-capacity-tb=1065` |
| LR-effcap-gbps | A positive real number | Sets the flitcap of the large region | `## All the maprules that were assigned to the LR in the previous iteration must be assigned to the large region in the current iteration as well Ticket-id = "NETOPT-431" Start-time = 1738325567 End-time = 1738325900 Region-number = [49440] LR-effcap-gbps=3000` |
| LR-effcap-multiplier | A positive real number | Multiply the flitcap of a large region by the specified value | `Ticket-id = "NETOPT-431" Start-time = 1738325567 End-time = 1738325900 Region-number = [49440] LR-effcap-multiplier=2`  |
| Sicky-map-bonus-coefficient | Any positive real number | This directive allows operators to override the default sticky map coefficients. The operators can provide a single maprule (and its corresponding sticky\_map\_bonus\_coefficients) or a list of maprules (and their corresponding sticky\_map\_bonus\_coefficients) | `## Set the sticky map bonus coefficients of maps “us” and “da2” to 5 and 10 resp. Ticket-id = "NETOPT-431" Start-time = 1738325567 End-time = 1738325900 Region-country = [“US”] Mapnames = [“us”, “da2”] Sticky-map-bonus-coefficient=[5, 10]` |
| Force-accept-disk-quota | A boolean. Either true or false | In the input validation step, we check if any maprule’s disk requirement has increased/decreased by more than X%. If yes, LeRoy abandons the current run and resorts to previous iterations maprule allocation. To override this behavior and let LeRoy accept the increased/decreased footprint requirement, we can set force\_accept\_disk\_quota=1 | `## Force accept disk quotas for the specified maprules Ticket-id = "NETOPT-431" Start-time = 1738325567 End-time = 1738325900 Region-geo = [“NA”] Mapnames = [“us”, “da2”] Force_accept_disk_quota = true` |
| Force-accept-poor-quality-fd | A boolean. Either true or false | In the input validation step, we abort maprule allocation if the FDs of the maps are of poor quality. By providing this override, the operator can direct LeRoy to ignore the quality of the FD for the maps. The operator can set  | `## Force accept disk quotas for the specified maprules even if the footprint descriptor quality was poor  Ticket-id = "NETOPT-431" Start-time = 1738325567 End-time = 1738325900 Region-geo = [“NA”] Maprule-names = [“us”] Force-accept-poor-quality-fd = true` |
| Force-accept-delta-in-traffic-input  | A boolean. Either true or false | In the input validation step, we abort maprule allocation for the region if a maps traffic jumped by a large amount. If we deem this jump to be okay, we can set this override to allow to bypass this check for the map | `## Accept large delta change in the traffic volume for d map.   Ticket-id = "LEROYOPS-58" Region-number = [51683] Mapnames = ["d"] Force-accept-delta-in-traffic-input = true` |
| LR-freeze-sticky-maps | A boolean. Either true or false | If set to 1, all the sticky maps will be assigned to the LR even if we do not have enough space on the LR. This will be done by reducing the disk quotas of all the maps till all the sticky maps can be squeezed in. Sticky maps are maps that were assigned to the LR in the previous iteration of LeRoy’s run. Note that this directive does not require and will ignore the Mapnames field if set.  | `Ticket-id = "NETOPT-431" Start-time = 1738325567 End-time = 1738325900 Region-geo = [“NA”] Maprule-names = [“us”] LR-freeze-sticky-maps= true`  |
| LR-Acknowledge-lost-region | A boolean. Either true or false | When a region that was assigned maprules in the previous iteration goes missing in the current iterations inputs, LeRoy continues to publish the previous iterations outputs for the region. If we want to stop this behavior and accept the fact that the region was indeed decommissioned, we need to set this override to true. | `Ticket-id = "LEROYOPS-2" Start-time = 1738325567 End-time = 1738325900 Region-number = [49440] LR-Acknowledge-lost-region= true` |
| LR-Accept-disk-capacity-drop | A boolean. Either true or false | If we observe a large drop in the large region’s capacity, say for instance a rack was removed, we will be cautious in making any changes to the maprule allocation. In such a case, we will revert to the previous iterations solution for the region. Once this override directive is set, we will accept the fact that we have lost capacity and the region and accept leroy’s new solution.  | `Ticket-id = "LEROYOPS-2" Start-time = 1738325567 End-time = 1738325900 Region-number = [49440] LR-Acknowledge-lost-region= true` |
| LR-Accept-flitcap-drop | A boolean. Either true or false | Same as above but for loss in flitcap | `Ticket-id = "LEROYOPS-2" Start-time = 1738325567 End-time = 1738325900 Region-number = [49440] LR-Accept-flitcap-drop= true` |

## 

