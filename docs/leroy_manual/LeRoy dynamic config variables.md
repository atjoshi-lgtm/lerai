# LeRoy Dynamic Configuration

| Author | What was updated | Date |
| :---- | :---- | :---- |
| Anirudh Sabnis Email: ansabni@akamai.com | Draft created | 2025-06-04 |

This document describes the dynamic configuration for LeRoy. The dynamic configuration lives on github in the following location: [https://git.source.akamai.com/projects/NETOPT/repos/leroy\_config/browse/config/dynamic\_config.json](https://git.source.akamai.com/projects/NETOPT/repos/leroy_config/browse/config/dynamic_config.json). The following table describes the available configuration parameters and their intended use-case. 

| Config\_property | Default Value | Description |
| :---- | ----- | :---- |
| large\_region\_disk\_occupancy\_margin | 1.05 | Margin multiplier for allowed disk occupancy in large regions. Leroy will consider the disk availability to be \<multiplier \* available\_disk\> |
| large\_region\_flitcap\_margin | 1.05 | Margin multiplier for allowed flitcap (network capacity) in large regions. Leroy will consider the available flits to be \<multiplier \* available\_flits\> |
| override\_file\_path | /opt/airflow/dags/lib/leroy/override.toml | Path to the TOML file containing override rules. |
| alert\_maprule\_offload\_discrepenacy\_threshold | 8 | Threshold for alerting on maprule observed vs expected offload discrepancies. |
| alert\_large\_region\_number\_machines\_diff\_threshold\_pct | 20 | Percentage threshold for alerting on change in number of machines in a large region. |
| alert\_large\_region\_disk\_capacity\_diff\_threshold\_pct | 20 | Percentage threshold for alerting on change in disk capacity in a large region. |
| alert\_large\_region\_flitcap\_diff\_threshold\_pct | 20 | Percentage threshold for alerting on change in flitcap in a large region. |
| alert\_maprules\_to\_allocate\_diff\_threshold | 3 | Threshold for alerting on the difference in number of maprules allocated to the large region in the current run. |
| abort\_maprules\_to\_allocate\_diff\_threshold | 5 | Threshold for aborting on the difference in number of maprules allocated to the large region in the current run. |
| alert\_maprule\_disk\_requirement\_diff\_threshold\_pct | 15 | Percentage threshold for alerting on change in maprule disk requirement. |
| abort\_maprule\_disk\_requirement\_diff\_threshold\_pct | 50 | Percentage threshold for aborting on change in maprule disk requirement. |
| abort\_minimum\_maprule\_disk\_requirement\_diff | 50 | Minimum absolute difference (TB) for aborting on maprule disk requirement change. |
| alert\_maprule\_traffic\_requirement\_diff\_threshold\_pct | 30 | Percentage threshold for alerting on change in maprule traffic requirement. |
| abort\_maprule\_traffic\_requirement\_diff\_threshold\_pct | 50 | Percentage threshold for aborting on change in maprule traffic requirement. |
| abort\_minimum\_maprule\_traffic\_requirement\_diff | 100 | Minimum absolute difference (Gbps) for aborting on maprule traffic requirement change. |
| alert\_number\_maprule\_diff\_in\_fcs\_output\_threshold | 3 | Threshold for alerting on the number of maprule differences in FCS output. |
| abort\_number\_maprule\_diff\_in\_fcs\_output\_threshold | 5 | Threshold for aborting on the number of maprule differences in FCS output. |
| alert\_number\_maprule\_diff\_in\_blc\_output\_threshold | 3 | Threshold for alerting on the number of maprule differences in BLC output. |
| abort\_number\_maprule\_diff\_in\_blc\_output\_threshold | 5 | Threshold for aborting on the number of maprule differences in BLC output. |
| alert\_disk\_churn\_in\_output\_threshold\_pct | 30 | Percentage threshold for alerting on disk churn in output. |
| abort\_disk\_churn\_in\_output\_threshold\_pct | 50 | Percentage threshold for aborting on disk churn in output. |
| alert\_monitor\_live\_machine\_diff\_threshold\_pct | 10 | Percentage threshold for alerting on live machine count difference. |
| monitor\_large\_region\_offload\_discrepenacy\_threshold | 8 | Threshold for monitoring offload discrepancy in large regions. |
| monitor\_large\_region\_cache\_occupancy\_discrepency\_threshold\_pct | 30 | Percentage threshold for monitoring cache occupancy discrepancy in large regions. |
| es\_cache\_quota\_1 | 7 | Quota for edge serial cache 1 (percentage or TB, context-dependent). |
| es\_cache\_quota\_2 | 1 | Quota for edge serial cache 2 (percentage or TB, context-dependent). |
| minimum\_disk\_quota\_pct\_for\_maprule | 1 | Minimum disk quota percentage for any maprule. |
| default\_sticky\_map\_bonus | 1000 | Default bonus coefficient for sticky maprules. |

| leroy\_output\_mode | automatic | Mode for Leroy output operation (e.g., automatic/manual). |
| :---- | :---- | :---- |
| alert\_large\_region\_disk\_capacity\_drop\_threshold\_pct | 20 | Percentage threshold for alerting on disk capacity drops in large regions. |
| alert\_large\_region\_flitcap\_drop\_threshold\_pct | 20 | Percentage threshold for alerting on flitcap drops in large regions. |
| mch\_lo\_disallow\_disk\_drop\_threshold\_tb | 50 | Threshold for disallowing drop in mch-ff-lo disk quotas. Specified in TBs |
| mch\_so\_disallow\_disk\_drop\_threshold\_tb | 50 | Threshold for disallowing drop in mch-ff-so disk quotas. Specified in TBs |

