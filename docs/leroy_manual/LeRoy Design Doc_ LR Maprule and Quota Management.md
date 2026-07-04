# LeRoy Design Doc: LR Maprule and Quota Management System

| Author | Anirudh Sabnis |
| :---- | :---- |
| Date created | February 28, 2025 |
| Contributors | Mangesh Kasbekar |

### I. Objectives

In the last year, we have deployed more than 20 Large Regions (LRs) across various tier-0 metros in the US and EMEA ([link](https://docs.google.com/document/d/1TZ1-hbYCGK32JJio6-3QI2typc3KwfnqoKIiJlMcq1M/edit?tab=t.0#heading=h.29dwogs0hxhh)) regions. In the coming year, we plan to deploy plenty more across the globe and the LRs are expected to serve a significant chunk of our network traffic.Thus, it is imperative for us to design a system that runs periodically to judicially decide which maprules will be served from the LRs based on the current network conditions and the maprule’s demands.  Furthermore, as LRs employ the RDC protocol ([link](https://docs.google.com/document/d/1sKDIpa7uGKrVWfwCqBrPpvMdJlzJVFMEMMQnuNg_WFU/edit?tab=t.0#heading=h.1bmgkfy2nmp2)) the system must calculate the disk-quotas for each maprule that will be served from them. This document provides the design for such a system.

**Current Approach**. The current approach of allocating maps is as follows (details in [link](https://docs.google.com/document/d/1qZanMtoRhfOpAPl6eSi2G1uMXbxS1aTkKN0K26iFqKY/edit?tab=t.0)).  Each large region has a region\_use\_type which could be one of the following: LR\_100G\_Server\_Region, LR\_10G\_Server\_Region, LR\_Mixed\_Server\_Region. For each region\_use\_type we define a static list of maprules to be assigned to the large region. This static list is loaded onto MROM and passed to BLC which sets the allowlists for the region. Further, disk quotas are computed by running a script manually and filing a ticket with FCS (for example, [FPOPS-206](https://track.akamai.com/jira/browse/FPOPS-206)). 

**Drawbacks**. The approach clearly is not efficient and has the following major drawbacks:

1) **Does not cater to LR diversity**. We now have LRs deployed across multiple metros with different hardware types and different server counts. It is inefficient to bucket LRs into just 3 region\_use\_types as there could be different optimal maprule assignments to the LRs.

2) **Does not cater to distinct maprule requirements in each metro**. The traffic demands and disk requirements of a maprule varies significantly across our metros. For example, we observe mm1’s traffic in Miami and not in any other city in the US. Thus, serving the same set of maps from all large regions of a region\_use\_type is inefficient. 

3) **Static and manual assignment**.   The assignment is not adaptive to changing network conditions.  Further, the assignment requires manual work, automation is preferred.

This document describes the design of LeRoy, a dynamic LR maprule allocation system that overcomes the above drawbacks and provides an efficient maprule management framework for Large Regions. We would like our system to have the following desired properties:

1) **Integrability.** The proposed system must integrate seamlessly with the existing maprule management systems such as BLC and FCS.

2) **Performant.** Must ensure good performance of the LR under any condition. For example, the traffic for a new maprule must be introduced gradually into the LR to warm up the cache. Otherwise, we would incur a sudden spike in the miss ratio. 

3) **Efficient use of resources.** Must be cognizant of the resource availability and use it judiciously. 

4) **Modular.** The system is composed of discrete components (modules) that can be developed, tested, and maintained independently.

5) **Maintainability.** The system can be updated, fixed, or improved over time with minimal risk of introducing new bugs.

6) **Safety.** Must adhere to the Change safety standards set by Akamai.

7) **Testability.** The system can be tested for bugs, performance issues. Includes unit tests, integration tests, etc.

8) **Observability.**  Should expose its internal state through logging, metrics, and tracing to facilitate monitoring and debugging in production.

### II. Design overview	

We now outline the high level flow for quota management in Large Regions. At the core of it lies an optimization model, the Maprule Placement Algorithm, that runs periodically to figure out which maps are assigned to which LRs. Further, at the periphery of the Maprule Optimizer, lie five other software components: 1\) LR Data Collector, 2\) Network observer, 3\) Input Overrider, 4\) Input Aggregator and Validator, 5\) Maprule Placement Algorithm, and 6\) Maprule Allocation Placer and Validator. 

The following diagram captures how the above components work together.

![][image1]  
                                                   Fig. 1\. LeRoy Architecture 

The responsibilities of the components (at a high level) are as follows,

1) **LR Data Collector.** Responsible for collecting the inputs required for the quota allocation. The various inputs include information such as LR disk and flit capacity, Traffic estimates of different maprules, disk requirements etc. More details will be provided in Section III.  
     
2) **Network Observer.**  Responsible for monitoring: 

   1) Observed offload of maps in LR  
   2) Traffic received by maps in LR  
   3) Live disk capacity and flit capacity of LR  
   4) Map flit usage  
   5) High F2B deviation of map from classic

   If any of the above deviates from what is expected, the Network Observer takes an appropriate action to counter the observed change. For example, if we observe less than expected offload for a map, the Network Observer will initiate a footprint descriptor computation for the map in the corresponding metro. This in turn will lead to allocating more disk space for the map in the metro. Further details are provided in Section IV. 

3) **Input Override**r. Facilitates manual intervention in maprule allocation. For example, an authorized person will be able to override the list of maprules that go into a region.  Further details in Section V.

4) **Maprule Placement Algorithm**. Given the required inputs, this algorithm decides which maps will be served from which large region in a given metro. This algorithm is run for all the metros which have Large Regions in them. Further details in Section VI.

5) **Maprule Placer & Validater.** This module first validates the output generated by the Maprule Placement Algorithm. If the solution is deemed not acceptable, the maprule placer will not make any quota adjustments or modifications to the current maprule allocation in a metro. If the solution is acceptable, the Maprule Placer will coordinate between FCS and BLC to ensure a safe propagation of the solution in the network. We will provide further details in Section VII.

We will now describe each component in detail. 

### III. LR Data Collector

This module collects data required to perform maprule quota allocation. The data is collected from various sources like mako, query, netopt input files, netarch etc., and stored on cplex09 in /ss3/netopt/databases/lr\_quota\_allocation/required\_info.db. Once the quota allocation algorithm finishes its run, the required\_info.db is copied to a info\_\<current\_timestamp\>.db and required\_info.db is deleted. Cplex09 is the machine where all the Netopt models are run. 

* **Maprules approved for LRs**.

  We are currently testing if a maprule is LR compatible by introducing the maprule in a test LR. The performance statistics of the maprule such as TAT, ghost rolls etc. are observed for an extended period of time before approving the maprule as LR compatible.   
  *Source*: The list of currently approved maprules is in the linked [document](https://docs.google.com/document/d/17quiy1Dy8H3wa524pCZ8DI8bFSQmfUf-OBOhfT5Wmr4/edit?tab=t.0#heading=h.adz1yv25y94). 

It is maintained in netarch in the following table: large\_region\_maprules. 

* **Maprules traffic requirement.**

  Projected traffic of the approved maprules in all metros with an LR.  
  *Source*: maprule\_large\_region\_demand table in /ss3/netopt/databases/netarch\_sync.db 

* **Footprint data.**

  The offload curves of the approved maps in the current quarter for all metros with an LR. We currently operate at the knee of the footprint descriptor curve from FD-Archive API. This will potentially be replaced by the cost-performance knees. We also record the quarter in which the footprint information was collected from.  
  *Source*: maprule\_knee from footprint.db. This db is populated once every day by querying FD-Archive 

* **Live traffic assignment by BLC.**

  Currently assigned maprules in the LR allowlist by BLC i.e., the set of current maprules being served by the LR  
  *Source:* MCM\_REGIONPREFERENCES in Mako  
    
* **Live peak traffic observed in LR.**

  We collect the peak observed traffic for each maprule over the last 14 days in each LR.  
  Source: MAPRULE\_TRAFFIC\_DAY tables in Mako.

  	

* **Live quotas set by FCS.**

  Currently set disk quotas in the LR by FCS.  
  *Source*: FCS will provide us the disk quotas through an API call.

* **LRs in the network.**  
   

A list of all the LRs in the network.   
*Source*: hw\_region\_table in /ss3/netopt/databases/dpdbs/" \+ get\_two\_quarters\_in\_future() \+ "\_all" database in Cplex09  
	

* **LR capacity.**

  Available flits (Gbps) and disk (TB) in the LR.  
  *Source*: Obtain hardware information i.e., disk size and effcap of the hardware deployed in the Large Region from local-base\_multiprovider.dat and use it to compute it’s total disk capacity and effcap. Local-base\_multiprovider.dat is obtained from Netopt’s git repository

* **Live LR capacity**. 

  We collect live LR capacity information. This accounts for suspended machines, suspended racks, etc. in the LR.  
  *Source:* From metrics.detail\_machines\_region\_summary under CMN\_INT schema in Netarch. 

* **ES cache quotas.**

  We currently operate 4 front end caches with a default quota of 7%, 1%, 1%, and 1%, respectively.   
  *Source*: table netopt.leroy\_es\_cache\_quotas in Netarch

* **Fraction of the disk space reserved for global LRU and ext4.**

  The default is 5% for global LRU, 1% for ext-4, and 2% for QLRU high. Lump the values together to 8%.   
  *Source*: table netopt.leroy\_ext4\_diskquota\_reservations in Netarch

* **Observed offloads in LRs**

  The observed offload and the disk occupancy of a maprule in a large region can be obtained from mako.  
  *Source*: maprule\_region\_footprint\_day in mako  
    
* **Expected offload in LRs**

	  
FCS populates the table lr\_expected\_offload\_and\_traffic\_by\_maprule with the expected   offload and traffic information into Query.   
	*Source:* lr\_expected\_offload\_and\_traffic\_by\_maprule in query.

* **Algorithm inputs for the previous iteration’s run.** 

  The above input data used in the previous run of quota allocation.   
  *Source*: The data will be available on cplex as well as on Netarch. We will have the following tables:  
  a) large\_region\_quota\_allocator\_maprule\_inputs: for each large region in the network it stores the maprule’s traffic and disk requirement. On netarch this table will be: netopt.large\_region\_quota\_allocator\_maprule\_inputs  
  b) large\_region\_quota\_allocator\_lr\_info: for each large region store its disk capacity and effcap. On netopt this table will be: netopt.large\_region\_quota\_allocator\_lr\_info

* **Algorithm outputs of the previous iteration’s run.**

  The FCS and BLC outputs created by the algorithm in the previous run.   
  *Source*:  The data will be Cplex as well as on Netarch. We will create the following tables:  
  a) leroy\_maprule\_allocation\_solution\_blc: contains the list of maprules assigned for each large region in the previous iteration of the maprule quota allocator/placer module  
  b) leroy\_maprule\_allocation\_solution\_fcs: contains the maprule quotas assigned for each large region in the previous iteration of the maprule quota allocator/placer module

In all the above cases we perform the following sanity checks after downloading the tables,

* Table is not empty  
* Table has a minimum number of rows

We then process the locally downloaded tables to obtain the information required for performing quota allocation. We perform the following sanity checks: 

**Input Validation for Alerts**. We create alerts under the following circumstances,

* A new LR is added or data for an existing LR is missing   
* Reject invalid region numbers. We make the following checks:  
  * Should not have alphabets  
  * Should not have special characters  
  * Should not be greater than 1,000,000  
* \+/- 20% change in disk capacity of an LR  
* \+/- 20% change in flitcap of an LR  
* \+/- 30% change in disk requirement of a maprule  
* \+/- 30% change in traffic estimates of a maprule  
* \+/- 3 maprules introduced.


Under any of the above specified conditions, we write the corresponding alert to the table netopt.lr\_quota\_allocation\_alerts in netarch. We will set up an alert mechanism on alerts.akamai.com to poll the above-mentioned table every 5 minutes. If any alerts are seen, alerts.akamai.com will mail us a digest of the created alerts. Upon receiving the alerts, the lr quota management operators can submit an override request. The override will be applied when the LR quota assignment re-runs the next time. 

**Input Validation for Aborting.** Revert to previous iterations quota allocation and create an override request under the following conditions,

* Missing disk and live traffic of a maprule  
* \+/- 50% change in disk requirement of a maprule  
* Poor footprint descriptor quality

### IV. Network Observer 

This module is responsible for monitoring the health of an LR and the performance of the maprules assigned to it. It runs periodically to collect the following statistics: 

* **LR Capacity**. Monitors if the LR’s capacity is lower or higher than the LR capacity that was used for the previous quota allocation for an extended period of time. This could mean that racks were suspended or machines were taken out of the region. It could also mean that new machines were added to the region. In such a case, we raise an alert. Specifically, we check if the LR’s median capacity has been lower or higher by more than 10% in the last 14 days. If the number of machines is lower, we will have to remove a few maps from the LR using overrides. If it is higher, we could introduce new maps into the LR using overrides. 

  Source: We obtain this information from the metrics.detail\_machines\_region\_summary table from the CMN\_INT schema in netarch. The table gives us the number of machines in a region that were down on a given day. The [linked document](https://wiki.deploy.akamai.com/wiki/Down_Machine_Categorization#up) describes when a machine is considered down for a given day. 

* **Expected Vs Observed Offload**. If the average observed offload of a map is lower (or higher) than the expected offload by more than 8% for over 2 weeks duration, we raise an alert. We also monitor the disk occupancy of a maprule in the large region. If the average disk occupancy is lower than the quotas set for the map by over 10% in the last 15 days, we will raise an alert.  

  Source: The expected\_offload.csv generated by the LR Maprule Placer component will be published to a query table lr\_expected\_offload\_and\_traffic\_by\_maprule table by FCS. The observed offload and the disk occupancy of a maprule can be obtained from the query in the [link](https://docs.google.com/document/d/1BrVNKku3aZ-FxtfqkWTxu4rw68IYnuwim-E8GkbLZ14/edit?usp=sharing).   

* **Planned Vs Observed Peak Traffic**. If the median observed peak traffic of a map is higher (or lower) than the expected peak traffic by more than 30% in the last 15 days, we raise an alert. 

  Source: The traffic for which the LR was planned is obtained from the lr\_expected\_offload\_and\_traffic\_by\_maprule table that is generated by LeRoy. This is compared to the actual peak traffic in the region. This information is obtained from MAPRULE\_TRAFFIC\_DAY tables. The table provides the peak traffic received by a maprule in a region for the last 30 days. 

Upon receiving an alert, the Ops team can submit an override request to make amendments. For example, upon observing a much lower than expected offload the Ops team can submit an override request to increase the disk quota of the maprule. The override mechanism is described in the section below.

### V. Input Overrider

In this section, we design the LR override mechanism that facilitates the Ops team to make manual overrides to the LR quota allocation inputs. For example, the Ops team could force a certain maprule to be served from an LR, disallow a certain maprule to be served from an LR, increase the disk quota of a maprule among other requests that we entail below. Further, these requests can be associated within a geographical scope. For example, the network operator can choose to disallow a certain map from being served from all the LRs in a specified country, geo or metro. We allow the following scopes: default, geo, country, metro, region.

Each override request is associated with a list of maprnames, override directives, and a geographical scope. We use the toml file format for specifying overrides. For example, an override request can be specified as follows:

```
[[override-records]]
## Exclude maps us, w25 to be served in the US
Ticket-id = "NETOPT-431"
Start-time = 1738325567
End-timestamp = 1739325567
Region-country = ["US"]
Mapnames = ["us", "w25"]
Access-control = "must-exclude"
```

#### 

If the override request pertains to attributes of the large region and not maprules, the override-record must not contain any Mapnames. For example,

```
[[override-records]]
## Set large regions disk capacity to 2PB
Ticket-id = "NETOPT-431"
Start-time = 1738325567
End-timestamp = 1739325567
Region-number = [50565]
LR-Available-Servers = [128]
```

####  V.I Override Directives

We provide the list of all the override directives and their descriptions in the [linked](https://docs.google.com/document/d/13EhiBOIRYzyBrLQdqfC9CKtodK9YAksChqJFPA5UHWk/edit?tab=t.0) document. 

#### V.II Override Geographical Scope

The geographical scopes are defined in the [linked](https://docs.google.com/document/d/13EhiBOIRYzyBrLQdqfC9CKtodK9YAksChqJFPA5UHWk/edit?tab=t.0) document. 

#### V.III Override Request Tree 

The override requests for each maprule can be parsed into a tree with each level specifying a geographical scope. The root of the tree contains the default overrides for the maprule across all regions in the world, while the leaves of the tree contain overrides specific to the region. The intermediate levels capture geographical scopes of geo, country, metro, region in that order. In order to apply overrides for a maprule and for a given LR, we search the tree depthwise and apply the deepest value for each directive. The below example demonstrates our approach. Consider the following override requests.

```
[[override-request]]
## Ban maprule us in France and Germany
Ticket-id = "LEROY-1"
Start-time = 172929992
End-time = 182929992
Mapnames = ["us"]
Region-country = [FR, DE]
Access-control = "must-exclude"

[[override-request]]
## Allow maprule 19 in Frankfurt
Ticket-id = "LEROY-2"
Start-time = 172929992
End-time = 182929992
Mapnames = ["us"]
Region-metro = "Frankfurt"
Access-control = "must-include"
```

Here, the first override request excludes maprule “us” from being served in France and Germany. However, the second override request marks the maprule to be allowed in the metro Frankfurt. Consider the LR 50565 (in Paris, France). The maprule “us” is excluded from the LR as the first override provides a must\_exclude directive for the maprule in France. Now, consider the LR 50527 (in Frankfurt, Germany). Here, maprule “us” is allowed in the LR as we have an allowed directive specified for Frankfurt even if there was a must\_exclude directive specified for Germany (DE). 

####  V.IV Override filing procedure  The overrides are filed as follows:  

* The master override directive lives on git.  
* Requester files a ticket for an override (add new or delete existing)  
* The Owner creates a PR to be approved by the requester and an additional approver.  
* Upon approval, Owner runs a sanity checker on the file, and upon successful sanity check, merges to the master git location  
* Adds the sanity check and git activity to the ticket and closes it.

At a low frequency (say once a month), we do a review of all the overrides to purge lines that we don't need anymore.

#### V.V. Maprule override conditions

Here, we list the conditions under which an operator must create override requests. The overrides are filed broadly based on the Network Observability (Sec. IV) and the LR’s input validation (Sec. III) alerts.  Further, the network operators can set overrides based on business recommendations such as disallowing a maprule from a metro/country or setting different sticky-map bonus coefficients. 

Observability based overrides:

* LR Capacity. The observer component observes live network conditions and fires an alert if we have lost or added capacity in a LR. The operator must create an override if the currently observed capacity is to be set as the LR’s capacity for quota computation. 

* Observed Vs Expected Offload. The operator must create the following override if the observed offload deviates significantly from the expected offload. The operator can use the quota\_multiplier or the quota\_tb directive to adjust quotas for the maprule. 

* Live traffic demand. The operator can set the demand\_multiplier or the demand\_gbps directive based on the observed live traffic for a maprule.

Input validation overrides:

* Missing disk and maprule demand requirement. If a certain maprule is missing disk or maprule demand information, it can be filled using an override request using the demand\_gbps or the quota\_tb directive. 

* \+/- 50% increase/decrease in a maprule’s disk requirement. To accept the increase/decrease the operator should set force\_accept\_disk\_quota=1 for the maprule in the override file. If not, the override can specify a suitable quota\_multiplier or quota\_tb. 

* Poor quality Footprint Descriptors. To accept poor quality footprint descriptors, set accept\_poor\_fds=1.

Business recommendation overrides:

Upon business recommendation, an operator can create overrides for the following scenarios.

* Increase/decrease sticky map bonus.   
* Force allow a maprule in a region/metro/country/geo.  
* Force disallow a maprule in a region/metro/country/geo.  
* Demand (traffic) multipliers for the maprules.  
* Quota multipliers for the maprules.  
* Freeze sticky maps.  
* Hard-code quota numbers for maprules.	

### VI. Maprule Allocation Algorithm

There will be two phases in the development of this algorithm. In the first phase, we find the best set of maps to add into the LR by solving an optimization problem as described in Algorithm 1\. If this algorithm removes a sticky map from the LR, i.e., it removes a map that was assigned to the LR in the previous iteration, we try to squeeze them back into the LR by adjusting (reducing) the quotas of the maps assigned by Algorithm 1\. This would be the phase 2 of the maprule allocation algorithm. 

#### Phase 1: Isolated LR Maprule Allocation Algorithm 

This algorithm aims to maximize traffic served from the LR without exceeding its disk and flit capacity. As the name suggests, this algorithm is run for each LR in isolation. 

```
Algorithm 1. Isolated Maprule Allocation Algorithm
Inputs: 1) N = Number of servers in the LR
2) T = LR's total disk space in TB
3) M = Approved maprules
4) S = Sticky maps
5) I = Must include maps
6) R = Must exclude maps7) D = Disk requirement for maps in M (in TB)
8) F = 85th percentile of the peak live traffic observed for the maprule in the last 14 days9) E = Effcap for maps in M for the hardware spec in the LR (in gbps)
Algorithm:Solve the below optimization problem.Initialize a vector of binary variables X. Variable xi \in X denotes if maprule mi in M will be served from the LR. Max. ∑i \in M fi xi  +  ∑j \in S kjfj xj  
st. 
1) ∑ dixi <= T      
2) ∑ (fi/ei)xi <= N 
3) xj = 1   ∀j in I 
4) xj = 0   ∀j in R 

```

##### Objective function  The objective function is the sum of two components. 

1) **Maximize traffic**. The first component i.e., (`∑i \in M fi xi`) aims to maximize the total traffic served by the LR.  

2) **Sticky map bonus**. The second component provides a bonus to allocate a sticky map. A sticky map is a map that is currently being served from the LR. We would like to continue to serve such a map from the LR. This is because if we remove the map from LR, there is a high chance the map’s traffic would have to be served from a classic region. The classic region may not have the map’s content cached and it could result in a huge degradation in performance due to cache misses. Further, if we replace a sticky map with another map, say *m*, the LR will not have map *m*’s content cached and we would observe performance degradation for *m.* Hence, we want to highly discourage adding/removing maps from an LR unless completely necessary.    
     
   The bonus is designed in such a way that a sticky map *j* is replaced if and only if we have a non-sticky map that is expected to receive at least kj\+1 times more traffic than the map it replaces. This is proved in Statement 1 below. We define a per map stickiness bonus coefficient kj to express the desired degree of stickiness of the map. This allows us to make some maps super-sticky if desired.  

##### 

##### Constraints

1) **Disk constraint**. The allocated maps should not exceed the disk capacity of the region.

2) **Flitcap constraint**. The allocated maps should not exceed the flit capacity of the region. 

3) **Must include maps**. Forcefully include maps specified in the MUST\_INCLUDE list.

4) **Must exclude maps**. Forcefully exclude maps specified in the MUST\_EXCLUDE list.

*Statement 1*. Algorithm 1 excludes a subset of sticky maps *S’ ⊂ S* from being served from the LR to include a set of non-sticky maps *N ⊂ M \- S*  if and only if ∑i \\in N fi  \>  ∑i \\in S ki fi  and the inclusion does not violate Constraints 1\) through 4).

*Proof*. This is true because including the maps in *N* increases the objective function in Algorithm 1 by the value ∑i \\in N fi  \-  ∑i \\in S ki fi, and is hence preferable. 

#### Phase 2: Sticky-map squeezer

The phase 1 of the algorithm may exclude some sticky maps from the LR.  As we know, this is undesirable. Hence, in this phase, we will try to squeeze the displaced sticky maps back into the LR by adjusting the quotas of the assigned maps. We will ignore the flitcap constraint as RM will adjust the traffic assigned to the LR such that the traffic volume does not exceed its flitcap. 

Note: This phase is optional and is only executed if we really do not want to remove any sticky map from the large region.

The algorithm runs iteratively. In each iteration, the disk space of all the maprule is reduced by 1%. This frees up disk space in the LR to squeeze the sticky maps. Note that in the first iteration we will not reduce the disk space which caters to the case where the LR was flitcap bound. As we are ignoring the flitcap constraint in this phase, it may result in adding back all the sticky maps. We find the best sticky maps to squeeze in using Algorithm 2 (described below). We iterate till all the sticky maps are squeezed in or we reach the min\_disk\_space threshold for all the maprules. The min\_disk\_space threshold will be decided by parsing the stdspace file of the maprule’s footprint descriptor. It will be set to a footprint value that provides (knee \- 3)% offload. Here, knee is the knee of the offload curve of the maprule as described in the document ([Knee Computation](https://collaborate.akamai.com/confluence/display/~mkasbeka/Finding+Knee+of+stdspace+curve)).

```
Algorithm 2: Sticky-map squeezer

Available_disk_space = T - (Sum of disk requirements of each assigned maprule)
i = 0

While (Exists unassigned sticky map AND
Each maprules disk occupancy > min_disk_space of the maprule)

Do:
1) Available_disk_space += (i * 1% of (sum of disk space occupied by all maprules whose disk occupancy is greater than it's min_disk_occupancy))

2) Subtract 1% from each maprule's disk occupancy whose disk occupancy is greater than it's min_disk_occupancy
	
	3) Solve the following optimization problem to add sticky maps into LR
	xi is the binary variable that determines if a sticky map is assigned to LR
	Max. 	∑i \in S' fi xi   // S' is the set of unassigned sticky maps
	st.    ∑i \in S' dixi <= Available_disk_space
	
Done
```

### VII. Maprule placer and validator  VII. I. Placer

The created solution must be coordinated between FCS and BLC. We have the following constraints:  

* To add a map, FCS first must allocate a quota for it in the LR. Then, BLC should add it to the region’s allowlist. BLC can add a map into the LR if there is enough free space in the LR to accommodate the map even if quotas are not set for it.  
     
* To remove a map, BLC must first remove the map from the region’s allowlist. Then, FCS can remove the quota for the map.

The pseudo-code below adheres to the above two constraints. The placer is run for each LR. 

```
Initialization

blc_prev_iter = blc output of previous run of maprule placer (this alg.)
fcs_prev_iter = fcs output of previous run of maprule placer 
''' The two variables blc and fcs will hold the maps that will be pushed out to BLC and FCS, respectively ''' 
blc = blc_prev_iter 
fcs = fcs_prev_iter
blc_live = Set of maps currently being served by LR
fcs_live = Currently set quotas for maps in the LR
Placement algorithm

''' Step 1) Remove quotas for maps that are not being served nor planned to be served from the LR.''' 
For m in approved_maps:
If (m in fcs) and ((m not in blc_prev_iter) and (m not in blc_live)):		Remove m from fcs''' Step 2) Find the best set of maps to fit into the LR '''blc_sol, fcs_sol = MapruleAllocator(lr_disk_avail, lr_flit_avail, approved_maps)

''' Step 3) Remove previously allocated maps from LR '''
If LR inputs have changed and LR is not new:	

	lr_disk_avail = Disk capacity of LR
	lr_flit_avail = LR effcap

	For m in approved maps:
		If (m in blc) and (m not in blc_sol):
remove m from blc 
''' Step 4) If there is space availabe in LR, add maps from blc_sol and fcs_sol into it. '''
Disk_space_available = LR disk space - Disk taken up by maps in fcs
Flits_available      = LR effcap - Flits used by maps in blc
// Change it to live
While Disk_space_available > 0 and Flits_available > 0:
Add map m from blc_sol to blc if m is not in blc
Subtract m's footprint requirement from Disk_space_available
Subtract m's	traffic from Flits_available

Verify that fcs is a superset of blc. If not, return fcs_prev_iter and blc_prev_iter 
```

##### Initialization 

* Initialize the current iterations solution (*fcs* and *blc*) to the previous iteration’s solution.   
  *fcs \= fcs\_prev\_iter, blc \= blc\_prev\_iter*   
* Get current set of maps in the large region’s allow list and store it in blc\_live  
* Get current set of maps that have quotas in the large region and store it in fcs\_live

##### Placement algorithm

*Step 1\)* Remove quotas for maps that are not being served nor planned to be served from the LR. 

If there is a map *m* in *fcs* that is not in *blc\_prev\_iter* and not in *blc\_live,* remove the map from *fcs.* This pertains to the case where BLC was asked to remove map *m* in the previous iteration and BLC has removed the map. Since the LR is not receiving any traffic for the map, we can remove it from FCS. 

The other possible cases are (i)  map *m* is in *blc\_prev\_iter* and not in *blc\_live.* This pertains to the case where the quota placer asked for *m* to be added to the LR in the previous iteration but BLC has not yet processed the request. In this case, we do not remove the map from fcs as we want to have quotas set for it. (ii)  map *m* is not in *blc\_prev\_iter* but in *blc\_live*. This pertains to the case when the quota placer asked for *m* to be removed from LR, but BLC has not yet processed the request. Thus we still need to have quotas for the map in FCS.

*Step 2\)*  We solve the maprule allocation problem (described in Sec. VI) for the entire LR to figure out the best set of maps to fit in. The results are stored in blc\_sol and fcs\_sol. 

*Step 3\)* If LR inputs have changed from the previous run or this is a new LR

We first check if inputs for the quota allocation changed in this iteration as compared to the previous iteration. The concerned inputs are: large region capacity (effcap and disk), list of maprules allocatable to LR, footprint requirements of the maprules, traffic estimates of the maprules. Now, if there is a map in blc that is not in blc\_sol, this map needs to be removed from blc. This is the only action we can take as we cannot add a map to blc without setting a quota for the map in FCS. 

*Step 4\)* Add maps to the LR if there is any spare capacity (flits and disk). First, evaluate available disk and effcap in the LR. If there is space capacity left in the large region, add maps from blc\_sol and fcs\_sol into the LR to fill the capacity. 

#### 

#### VII. II. Validator

This module first validates the solution produced by the maprule allocation algorithm and then coordinates the solution with FCS and BLC. We perform the following validation steps for each Large Region:

* Compare quota allocation to the previous iterations solution and create alerts if

  1\. \+/- 5 number of changes

  2\. \+/- 30% total quota change

  3\. \+/- 35% total bits change

* We will revert to the previous iterations solution if the change is quite a bit. We will create an override request to accept/reject the change. 

  	1\. \+/- 8 number of changes  
  	2\. \+/- 50% total quota changes

#### VII. III. Expected offloads

We should publish the output of LR maprule placer and quota to a Query table. However, it is hard to publish data to query from the cplex09 machine. We will create an expected\_offload.csv file and push it to git. While FCS reads the fcs.csv, it will also read the expected\_output.csv and publish it to Query. The file format is:

\< Timestamp, region number, map name, TB quota requested, % quota requested, offload expected, Traffic expected\>

#### VII. IV. Outputs

LeRoy publishes three output files,

- Fcs.csv (described in [link](https://docs.google.com/document/d/1q3NrEXdVKy7Hh8uq96i_GTmZrXmOVsE0672S5ua-_ew/edit?tab=t.0#heading=h.8dohtslyt269))   
- Blc.csv (described in [link](https://docs.google.com/document/d/1dBVDpGtnw8zIW7kzE8aK4Isu_5GhDwGZ8OytOBwA6yU/edit?tab=t.0#heading=h.8dohtslyt269))  
- Expected\_offload.csv (described in [link](https://docs.google.com/document/d/1DCDYw2rDTVLoD74GucOHKeZS83ginnD9oilTgNarnIE/edit?tab=t.0#heading=h.8dohtslyt269))

Further, LeRoy also writes its output to Netarch in the following tables:

- FCS ([linked](https://netarch.akamai.com/s/a29f0efb))  
- BLC ([linked](https://netarch.akamai.com/s/1f033602))

### VIII. Meeting the maprule management requirements

The aforementioned design tackles the requirements set in the requirements document ([link](https://docs.google.com/document/d/1qZanMtoRhfOpAPl6eSi2G1uMXbxS1aTkKN0K26iFqKY/edit?tab=t.0)). In particular, 

* It proposes a system that assigns maprules to the LRs based on their capacity and the footprint and flit requirement of the maprules in the LR’s metro. 

* The system adapts to changing network conditions and traffic requirements to find optimal maprule allocation for the LR.

* The system coordinates the solution between FCS and BLC to ensure a safe and smooth introduction and removal of maprules from an LR. 

* It provides an interface for the Ops team to override the current maprule allocation.

[image1]: <data:image/png;base64,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>