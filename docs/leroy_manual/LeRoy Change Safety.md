# LeRoy Change Safety Document

| Authors | What was updated | Date |
| :---- | :---- | :---- |
| Anirudh Sabnis Email: [ansabni@akamai.com](mailto:ansabni@akamai.com) Mangesh Kasbekar Email: mkasbeka@akamai.com | Draft created | 2025-06-04 |

### 1\. Links and References 

* Leroy design document: [https://docs.google.com/document/d/1mnfX-198UzgnnszzpuvUpCufNXebzNHcBHC3faAEaVM/edit?tab=t.0\#heading=h.5idd4gz77qzi](https://docs.google.com/document/d/1mnfX-198UzgnnszzpuvUpCufNXebzNHcBHC3faAEaVM/edit?tab=t.0#heading=h.5idd4gz77qzi)

* Leroy override definitions documentation: [https://docs.google.com/document/d/13EhiBOIRYzyBrLQdqfC9CKtodK9YAksChqJFPA5UHWk/edit?tab=t.0\#heading=h.1kkp5m6cgib8](https://docs.google.com/document/d/13EhiBOIRYzyBrLQdqfC9CKtodK9YAksChqJFPA5UHWk/edit?tab=t.0#heading=h.1kkp5m6cgib8)

* Leroy dynamic config documentation:  
  [https://docs.google.com/document/d/1aNNHPb674fccg0nju3Gg8zdqgz6AC7qR7lBVqJs9XiQ/edit?usp=sharing](https://docs.google.com/document/d/1aNNHPb674fccg0nju3Gg8zdqgz6AC7qR7lBVqJs9XiQ/edit?usp=sharing)   
    
* A few examples of override updates and how they are handled:  
  [https://docs.google.com/document/d/1M9JzOGdBgdOwPmWrHx5-qJ5rp5pSTPUo-c9Au\_wOtpA/edit?tab=t.0](https://docs.google.com/document/d/1M9JzOGdBgdOwPmWrHx5-qJ5rp5pSTPUo-c9Au_wOtpA/edit?tab=t.0) 

### 2\. Acronymns and Definitions

| Acronym | Definition |
| :---- | :---- |
| FCS | Footprint Control Service. Responsible for creating maprule quota configurations and pushing the configurations on to Akamai’s network |
| BLC | Business Logic Configurator. Responsible for creating maprule allowlists that dictate which regions can serve the maprule’s traffic |
| LR | Large Region |

### 3\. LeRoy: a brief introduction 

Large Regions (LRs), as the name suggests, are regions with a sufficiently large number of machines \~100 to 128 and considerably higher numbers in the near future. In this document, the regions apart from Large Regions will be referred to as classic regions. A distinguishing feature of Large Regions from their classical counterparts is that we assign disk quotas to each maprule that is served from the region. The footprint or the disk needed to attain a target offload varies with each maprule in each metro. Thus, enforcing a quota for each maprule helps us provide offload/performance guarantees for it. While the current maprule assignment system, BLC, solves the maprule assignment problem for classic regions there does not exist a solution for Large Regions. 

**LeRoy: Maprule management in Large Regions**. LeRoy (design document: [link](https://docs.google.com/document/d/1mnfX-198UzgnnszzpuvUpCufNXebzNHcBHC3faAEaVM/edit?tab=t.0#heading=h.5idd4gz77qzi)) is a new component responsible for managing maprules in Large Regions. Leroy runs periodically (every day) to decide which maprules will be served from the Large Region and also decides how much disk quota to allocate for it. It makes this decision based on various factors such as expected traffic, disk requirements, flits, live traffic of the maprules etc. It further coordinates this solution with BLC and FCS. To BLC, it provides blc.csv that contains a list of \<region, maprule\> tuples that specify the maprules that must be served from each large region. It also writes the same output to the [netarch table](https://netarch.akamai.com/s/ef2e9dda) netopt.leroy\_maprule\_allocation\_and\_quotas\_for\_blc. To FCS, it provides fcs.csv that contains a list of \<region, maprule, quota\> tuples which specify how much disk quota to assign for each maprule in each large region.   

* **BLC.** A component developed and maintained by the Mapping Strategy team that creates region allowlists for each maprule and these allowlists dictate which regions in our network can serve which maprule. Upon receiving a maprule allocation solution blc.csv ([linked](https://docs.google.com/document/d/1dBVDpGtnw8zIW7kzE8aK4Isu_5GhDwGZ8OytOBwA6yU/edit?tab=t.0#heading=h.8dohtslyt269)) from LeRoy, BLC updates the allowlists to reflect LeRoy’s solution i.e., it adds or removes the Large Region from the maprule’s allowlist. Further, it reassigns the classic regions by accounting for the fact that the maprule will be served or not served from the Large Region. 

* **FCS.** A component developed by the mapping team that is responsible for creating and  pushing disk quota configuration files to all machines on our network. Upon receiving an fcs.csv ([linked](https://docs.google.com/document/d/1q3NrEXdVKy7Hh8uq96i_GTmZrXmOVsE0672S5ua-_ew/edit?tab=t.0#heading=h.8dohtslyt269)) from LeRoy, FCS modifies ghost caching metadata files fpdata.xml and fpstrategy.xml to reflect the disk quotas requested by LeRoy and pushes it out to the network. 

**Coordination between FCS and BLC.** While creating the inputs for FCS and BLC, LeRoy makes sure that for each maprule in each region:

* Leroy removes quotas for a maprule from a region only after BLC has removed the region from the maprule’s primary tier allowlist.  
* Leroy adds a map into the LR by adding it to fcs.csv and blc.csv simultaneously. It would do so only after ensuring that there is enough free disk space available for the map in the LR i.e., the current disk quotas for the other maps and the disk quota required for the map being added do not together exceed the disk capacity of the region.

There are however exceptions to the above rules. For example, we do not cache content belonging to API traffic maps and no-store maps and hence, we do not allocate quotas for them. For such maprules, we need not ensure that we have disk quotas for the maprule in the region. 

#### 3.1 LeRoy instances 

Conceptually, there will be three instances of LeRoy: Production, Staging and dev. An instance can run daily on an airflow dag on cplex09, and it can also be invoked in an offline manner from commandline. These instances all run on prod-perf-cplex09.bos01.corp.akamai.com.

| Instance | Purpose | Output locations |
| :---- | :---- | :---- |
| Production dag | Main production instance | [Production output git location](https://git.source.akamai.com/projects/NETOPT/repos/lr_quota_allocation_outputs/browse)Netarch table netopt.leroy\_maprule\_allocation\_solution\_blc In manual promotion mode:  [Production manual promotion git location](https://git.source.akamai.com/projects/NETOPT/repos/lr_quota_allocation_outputs_manual/browse) |
| Production offline | Change safety procedure of modification to overrides | [Offline output git location](https://git.source.akamai.com/projects/NETOPT/repos/lr_quota_allocation_outputs_manual_offline/browse)No insertions into Netarch table |
| Staging dag | Testing of new features (uncommon use) | [Staging output git location](https://git.source.akamai.com/projects/NETOPT/repos/lr_quota_allocation_outputs_test/browse)No insertions into Netarch table |
| Staging offline | Testing of new features, regression test-suite (common use case) | [Offline output git location](https://git.source.akamai.com/projects/NETOPT/repos/lr_quota_allocation_outputs_manual_offline/browse)No insertions into Netarch table |
| Devoffline | Developer’s workspace(s)(common use case) | [Offline output git location](https://git.source.akamai.com/projects/NETOPT/repos/lr_quota_allocation_outputs_manual_offline/browse)No insertions into Netarch table |
| Dev dag | Will not be used | N/A |

### 4\. Scope

### This document describes the safety standards we will adhere to while making any changes to the code, config, and overrides of LeRoy. In particular, this document will specify the procedures carried out for the following changes: 	

* Updates to LeRoy’s dynamic config and override file  
* Code update: feature rollout and version upgrade

The procedures thus laid out will comply with the safety principles listed in the safety strategy [guidelines](https://docs.google.com/document/d/1HRtVgOJmQnOeJO8uH91pPfzzkW0zcNrm9JCu8D4vdwA/edit?tab=t.0#heading=h.a71rneb7jlna) document. As required by the guidelines, we will first briefly discuss the principles and our approach to abide by them. 

* Documentation. We will include (i) procedure to describe how a change is performed which includes filing of a jira ticket, defining roles, approval policy etc., and (ii) documentation of the occurrence of the change that includes how a change is monitored, rolled back and propagated in the network. 

* Prequalification. We will describe the procedures involved in verifying a certain change before rolling it out on the network.

* Incremental change deployment.

* Metrics and success criteria. We will describe how a change is monitored once rolled out. We will describe the alerts that we would have in place to monitor the change and the netarch/query tables to which LeRoy writes its results. 

* Impact. We will describe how other systems are impacted by a change in LeRoy’s output and how changes made in other systems can impact LeRoy. 	

### 5\. Dynamic configuration changes and Override requests

LeRoy’s behavior can be tweaked by updating the dynamic\_config.json or the override.toml files located in the git repository ([link](https://git.source.akamai.com/projects/NETOPT/repos/leroy_config/browse)). The specifics of each parameter in the dynamic\_config.json and override.toml are in [link-A](https://docs.google.com/document/d/13EhiBOIRYzyBrLQdqfC9CKtodK9YAksChqJFPA5UHWk/edit?tab=t.0#heading=h.k8y19iqkfmri) and [link-B](https://docs.google.com/document/d/1aNNHPb674fccg0nju3Gg8zdqgz6AC7qR7lBVqJs9XiQ/edit?tab=t.0), respectively. In this section, we will describe the processes involved in updating the configuration parameters and overrides.

#### 5.1. Owners and responsibilities

The following groups exist to facilitate LeRoy operations. For each of these groups, there is also a JIRA username. 

| Group | People | Role  | Mailing-list |
| :---- | :---- | :---- | :---- |
| leroy-dev | [Anirudh Sabnis](mailto:ansabni@akamai.com) [Mangesh Kasbekar](mailto:mkasbeka@akamai.com) | Author, Reviewer, Deployer, Monitor | dl-leroy-dev@akamai.com |
| leroy-ops | [Anirudh Sabnis](mailto:ansabni@akamai.com) [Mangesh Kasbekar](mailto:mkasbeka@akamai.com) [Bruce Chen](mailto:ychen@akamai.com) [Atalay Kutlay](mailto:akutlay@akamai.com) [Hung-Yu Lee](mailto:hulee@akamai.com) | Reviewer, Monitor  | dl-leroy-ops@akamai.com |
| leroy-notify | [Anirudh Sabnis](mailto:ansabni@akamai.com) [Mangesh Kasbekar](mailto:mkasbeka@akamai.com) [Bruce Chen](mailto:ychen@akamai.com) [Atalay Kutlay](mailto:akutlay@akamai.com) [Hung-Yu Lee](mailto:hulee@akamai.com) [Abby Men](mailto:hmen@akamai.com) [Ameya Hate](mailto:amhate@akamai.com) [Steve Chiu](mailto:stchiu@akamai.com) [Scott Roche](mailto:scroche@akamai.com) [Dahlia Nadkarni](mailto:dnadkarn@akamai.com) | Participant | dl-leroy-notify@akamai.com |

#### 5.2. Roles

| Role | Description | Who/Which team |
| :---- | :---- | :---- |
| Requester | Submitter of the change request. Is aware of the business justification of the change. Submits a jira ticket requesting the change.  | Leroy, Mapping Strategy, or FCS. Any escalation from outside these groups will be rejected, redirecting the requester to the established mapping-strategy intake process |
| Author | Person who creates a change in the dynamic\_config.json or override.toml files and submits a pull request for the corresponding change. Performs offline checks to verify that the change does not cause any disruptions in the network  | leroy-dev |
| Reviewer | Person who reviews the change and approves the change | leroy-ops, additional reviewers from the mapping strategy team if the requested change results in removing a map from a region, and additional reviewers from fcs-dev if the change involves increasing/decreasing quotas of a map.  |
| Deployer | Person who merges the pull request and hence, deploys the change to the network | leroy-dev, leroy-ops |
| Monitor | Person who monitors if a certain change was safely propagated on to the network and the network responded as expected.  | leroy-ops, [Abby Men](mailto:hmen@akamai.com), [Ameya Hate](mailto:amhate@akamai.com), [Steve Chiu](mailto:stchiu@akamai.com), [Scott Roche](mailto:scroche@akamai.com), [Dahlia Nadkarni](mailto:dnadkarn@akamai.com) |
| Verifier | Person who verifies the success of the change. This would either be the requester or the author. | leroy-ops |
| Participant | Person who is part of the leroy-notify mailing list. The participant receives information about the override/config change requests.  | leroy-notify |
| Coder reviewer | Person responsible for reviewing code changes made to LeRoy. Code reviewers approval is required for merging the changes to the master production branch.  | leroy-dev, [Atalay Kutlay](mailto:akutlay@akamai.com), [Scott Roche](mailto:scroche@akamai.com)  |

#### 5.3. Procedure to update config/overrides

The steps involved in updating the configs or overrides are as follows:

1. The requester creates a ticket on Jira under [LEROYOPS](https://track.akamai.com/jira/projects/LEROYOPS/issues/) requesting for an update to either the override.toml file or the dynamic\_config.json. The requester must provide sufficient justification and information about the change. JIRA will automatically add  dl-leroy-notify as a Participant.  All participants in the ticket are notified by Jira at every stage of the process.  
      
2. The author uses the production offline instance of LeRoy to make the requested change, and test it. The author makes the required changes to dynamic\_config.json or override.toml (whichever is requested) that are in the [linked](https://git.source.akamai.com/projects/NETOPT/repos/leroy_config/browse?at=refs%2Fheads%2Foffline_test_branch) git repository.   
     
3. The author then runs the offline version of LeRoy by invoking the compute\_quota\_offline.py script. This produces outputs in the [offline output git location](https://git.source.akamai.com/projects/NETOPT/repos/lr_quota_allocation_outputs_manual_offline/browse). The author compares the outputs to the production outputs in [production output git location](https://git.source.akamai.com/projects/NETOPT/repos/lr_quota_allocation_outputs/browse). While it’s not possible to list of the exact comparisons that will need to be made at this time, we expect the following broad categories:  
     
   * Input override check: The requested change may be to override certain values present in the input. The author verifies if the inputs were overridden appropriately.   
     	  
   * Output diff check:   
     * The author examines the maprule assignment produced by LeRoy in [blc.csv](https://git.source.akamai.com/projects/NETOPT/repos/lr_quota_allocation_outputs_manual_offline/browse/blc.csv) in the [offline output git location](https://git.source.akamai.com/projects/NETOPT/repos/lr_quota_allocation_outputs_manual_offline/browse). The author identifies the change to maprule assignment compared to the production assignment, and  verifies that the overrides have behaved exactly as intended.   
     * The author examines the quotas allocated to each maprule in [fcs.csv](https://git.source.akamai.com/projects/NETOPT/repos/lr_quota_allocation_outputs_manual_offline/browse/fcs.csv) in the [offline output git location](https://git.source.akamai.com/projects/NETOPT/repos/lr_quota_allocation_outputs_manual_offline/browse). The author identifies the change to quotas compared to the production quotas. Small changes to quotas are always expected, so the focus here would be on identifying large deviations. The author verifies that overrides have behaved exactly as intended. 

   * The author uses the FCS API (as described in Section 3.4 and Section 6.1 in the [link](https://collaborate.akamai.com/confluence/pages/viewpage.action?spaceKey=MAPENG&title=FCS+3.3+-+Support+for+Large+Regions+Maprule+Management)) to verify if the newly created fcs.csv will be accepted by FCS without errors. 

The document [linked](%20https://docs.google.com/document/d/1M9JzOGdBgdOwPmWrHx5-qJ5rp5pSTPUo-c9Au_wOtpA/edit?tab=t.0#heading=h.onni3v260fy7.) provides a playbook for commonly used override requests.

4. The author documents the observations on the Jira ticket, providing sufficient details regarding LeRoy’s output and inputs. For instance, the author pastes the relevant parts of the fcs.csv and blc.csv solution produced by the above script to the ticket. 

5. When the change is validated, the author now creates a pull request to merge the changed dynamic\_config.json or override.toml (whichever is requested to be changed) from the offline version of the files to the production files. The author adds a reviewer from the LeRoy-Ops team. The author and the reviewer must be two distinct individuals. 

6. The reviewer reviews the change, checks the output pasted by the author and approves the change if everything is in order. 

7. Once the change is approved, the deployer merges the change to the production branch. LeRoy picks up the updated config changes in its next run. The deployer updates the ticket stating that the change has been merged. 

8. The author monitors LeRoy’s run over the next 2 daily runs, using the metrics and success criteria described below in section 5.4. The monitor updates the ticket with sufficient details on the analysis performed.   
     
9. The change is then deemed successful by the verifier by looking at the updates made to the ticket by the author, reviewer, deployer, and the monitor.  The verifier then closes the ticket.

#### 5.4. Metrics and success criteria

Here, we describe the steps performed in order to monitor the change over the next two daily runs. 

* Has FCS picked up the change?   
  * Present (indirect) method: Monitor the updated quota using the table footprint\_stats\_rv on query. The footprint\_stats\_rv table displays the current disk quotas in the region. An alternate way to verify if the change was picked up by FCS, is to use the FCS API (Section 5.2 in [link](https://collaborate.akamai.com/confluence/pages/viewpage.action?spaceKey=MAPENG&title=FCS+3.3+-+Support+for+Large+Regions+Maprule+Management)) to return the deployed fcs.csv. If it is identical to the one submitted, it means FCS has pushed out the changes.   
  * Future (direct) method: Under [FPCONTROL-332](https://track.akamai.com/jira/browse/FPCONTROL-332), FCS will provide a new functionality to answer the question “Has FCS pushed out the fcs.csv that LeRoy created at timestamp T?” This method will be used instead of the indirect method.

* Has BLC run since we made a change, and if so, has BLC picked up the change?   
  * This can be discovered based on netarch queries like [https://netarch.akamai.com/s/497d2a19](https://netarch.akamai.com/s/497d2a19) and  https://www.nocc.akamai.com/miniurl/?id=287dd

* Is the network adjusting to the change?   
  * If a new map is introduced into or removed from a large region, are we seeing traffic for the map in the large region? Monitor the region’s traffic on [loadgraphs](https://lg.netarch.akamai.com/cgi-bin/loadgraphs).  
  * If the quota for a map on a large region was changed, are we observing the desired offload for all the maps in the region? We can monitor the offloads on [the offload page on perf.akamai.com](https://perf.akamai.com/maprule_management/offload.html). 

* Has the change caused undesirable outcomes in the large region?  
  * Monitor the change management dashboards to look at an increase in the number of ghost rolls and flit-to-bit ratio. Flit-to-bit ratios also can be monitored on the [f2b page on perf.akamai.com](https://perf.akamai.com/maprule_management/f2b.html). 

Whether the change has given rise to network-level undesirable outcomes (such as link overloading and packet losses) is a little hard to monitor given data sources related to packet losses are disconnected from maprule level changes, and packet losses can have multiple factors. We do not propose to include that monitoring as part of monitoring the effects of LeRoy’s changes. We are working with the Network Specialists team to include information related to LeRoy’s actions in their procedure to follow up on alerts related to packet losses.

#### 5.5. Reverting a change during emergency

If we observe an undesirable outcome when LeRoy’s outputs are pushed onto the network by FCS and BLC, we will need to have a mechanism to counter the outcome immediately. 

Our common and most effective emergency response is to suspend a maprule from a set of regions. When that is not feasible or effective, emergency response may have to be achieved by using the three components LeRoy, FCS, and BLC in a manual emergency run mode. 

* LeRoy: The airflow dag provides a manual run option that is authorized to be run by leroy-ops. This triggers a manual run of LeRoy immediately.  
* FCS: Will provide a “do run now” API endpoint to FCS SMEs ([FPCONTROL-327](https://track.akamai.com/jira/browse/FPCONTROL-327)).   
* BLC: already has the functionality to remove a region from the maprule’s allowlist manually. The change is picked up by MCM, it runs its checks and pushes it out RA. If there are no violations in those checks, the change will be effective in a few minutes.

#### 5.6. Reverting a change under normal circumstances

The process to revert a change is similar to creating a change. We expect the requester to submit a change request through Jira. Once submitted, we would follow the same steps as described above.

#### 5.7. Audit trail 

The information regarding the changes made with respect to the change request can be obtained from the corresponding Jira ticket. The comments on the Jira request will contain all the information regarding the processes and validation performed in order to approve the change request. The Jira ticket also contains links to the specific git commits made for the change. This happens automatically as any git commit made to LeRoy’s master repository must contain an associated Jira ticket identifier in the commit message. The git commit, therefore, gets linked to the jira ticket.

The BLC and FCS outputs produced by Leroy for any particular date can be viewed on netarch using the below queries. Here, the date should be in the format {YYYY}-{MM}-{DD}. Do not forget to add in zeros to fill in all the digits. 

```sql
select 
    * 
from 
    netopt.leroy_maprule_allocation_solution_fcs 
where
    created_at like "{YYYY}-{MM}-{DD}%"

```

```sql
select 
    * 
from 
    netopt.leroy_maprule_allocation_solution_blc 
where
    created_at like "{YYYY}-{MM}-{DD}%"
```

### 

### 6\. LeRoy instances and SDLC

#### 6.1 LeRoy instances

Same as section 3.1. 

#### 6.2 Software Development Life-Cycle

All the code change requests are first requested as a ticket on JIRA under the following [link](https://track.akamai.com/jira/projects/LEROY/issues/LEROY-6?filter=allopenissues). A LeRoy version will be planned as a set of tickets. The code development for each ticket will be performed on a dev instance. Multiple dev instances will be allowed. 

**Development process**  
For each ticket, the developer will follow the following development process:

1. The developer will perform code development using a branch of the production branch.  
2. The developer will run unit and regression tests, and ensure all the tests pass. If any regression test fails, due to the current changes, the developer will make sure that the failure is legitimate. If legitimate, the developer will fix the test case. The developer will compare the outputs of the dev environment to the production outputs and ensure that the outputs are equivalent. In case the output of the dev environment is different from production outputs (different maprules or different quotas), the developer will make a judgment call if this difference is acceptable or not. If not, the developer will fix any bugs till an acceptable output is produced.   
3. To merge the change from the dev branch to the production branch, the developer will create a pull request, and specify a code reviewer for the pull request. Code reviewers are mentioned in Section 5.2. The output of unit tests and output comparison will be made available to the reviewers. The reviewer will read the code, examine the testing outputs, and approve the change if appropriate.  
4. Upon successful code review, the developer will be allowed to merge code to the production branch. They may do so for each ticket individually or batch multiple tickets together. The developer can now close the ticket(s). 

(Note that adding the code to the production branch does not mean that the code starts running on the production instance of LeRoy. It needs to be explicitly deployed there. The deployment process is described below in this document.)

**Release qualification**  
We could be deploying a new version or an older version of LeRoy on the production instance. Aims of release qualification are: 

1. When a release is being qualified for moving production to a new version, the qualification is meant to check if the collection of all the newly added features works well together, and the present inputs, dynamic config, and overrides are processed correctly by the new version.   
2. When a release is being qualified for moving production backward to a previous version, then the code of the previous version is already qualified. The qualification is to make sure that the code processes the present inputs, dynamic config, and overrides correctly.

Qualification steps

1. When testing for qualification of a future release, testing on the staging instance does not necessarily happen after adding the code for each ticket into the production branch. It can happen after all the tickets of the version are closed.   
2. For qualifying a release on staging, the developer will deploy the code under the new version tag from the production branch on the staging instance. The developer will rerun regression tests in this instance. If execution correctness issues are discovered, then existing tickets will be re-opened or new tickets will be filed to fix the code, static/dynamic config or overrides.   
3. The developer will compare the outputs of the staging environment to the production outputs and ensure that the outputs are equivalent. In case the execution is correct but the output of the staging environment is different from production outputs (different maprules or different quotas), then the developer will request an approval from the members of the mapping-strategy team and/or the FCS team. The approval request and the subsequent approval will be made on the development ticket filed for the code change.   
4. After all the tickets in a planned release are closed, and the testing on the staging instance is completed, the developer will push a version tag to the production branch, marking the creation of a new version.  
5. In the case of qualifying a previous release with the current static/dynamic config and overrides, fixes required to dynamic config and overrides can be made using the above-described process without needing a new version tag.

**Deployment** 

1. A LEROYOPS deployment ticket will be created for the deployment of a release whose software development is complete.   
2. After the creation of the new version tag, the new release from the production branch may be deployed to the production instance using a git pull of that tag.  
3. Deployment can only occur during a designated time window outside of LeRoy’s daily dag schedule.  
4. The following steps will be taken in the deployment of a release  
   1. LeRoy’s daily execution dag will be paused using the Airflow UI  
   2. The code for the new version will be installed using the deployment script   
      1. No specific change needs to be made for static/dynamic configs and overrides, since LeRoy pulls the latest ones from git at the start of each daily run  
   3. LeRoy’s daily execution dag will be unpaused using the Airflow UI  
6. Monitoring will be required for two daily runs following the release. The developer will monitor LeRoy’s outputs after the release has been deployed on the production instance:   
   1. Monitor if BLC and FCS are picking up the newly generated outputs and that the output does not create undesirable outcomes i.e., BLC and FCS are not rejecting LeRoy’s outputs.  
   2. LeRoy runs without failure (taking too long to run, dag failure, input validation failure or output validation failure) in the production environment.   
   3. Monitor for any LeRoy alerts that fire in those two daily runs.   
7. Upon successful monitoring, the release is considered deployed, and the developer will close the ticket for the deployment of the release.

**Exception**  
If a single small code fix is required (commonly understood as urgent and out-of-order with the release cycle), then the entire process above meant for multiple tickets in a release is a time-consuming overkill. In such cases, skipping the staging instance and merging a fix from a developer instance that mimics the production instance to the production branch is allowed. The code review process described above is sufficient to verify the fix.

### 7\. Timing

LeRoy runs 5 days a week from Monday-Friday at 11am ET. This gives sufficient time for LeRoy-Ops to monitor new allocations made by LeRoy on any given day. 

### 8\. Monitoring and Alerts

The outputs produced by LeRoy have significant consequences on how we serve traffic on our network. For example, if LeRoy decides to remove a large traffic maprule from a large region, this will have dire consequences as traffic close to several hundred Gbps will now have to be served from the other smaller regions in the metro which may not be able to handle the high volume traffic. Further, these regions will not have the maprule’s content cached and will create a significant load on our ICN links. Thus, we actively monitor each LeRoy run to make sure that its inputs are legitimate, and its outputs do not cause a huge change in traffic being served from the region resulting in undesirable traffic allocation. In each such case, LeRoy reverts to the previous iterations allocation for the region i.e., it blocks the current iterations allocation for the region and raises an alert on [alerts.akamai.com](http://alerts.akamai.com). A list of all the alerts that LeRoy fires in adjunction with ADMS can be found on this [ADMS alert search link](https://alerts.akamai.com/adms/advanced_find.jsp?alert_name=%5BLeRoy%5D&match_alert_name=substring). The presently active alerts can be monitored on this [Alert Reporter link](https://alerts.akamai.com/cgi-bin/reporter/alertreporter?__option_summary_collate_by=percent&report_type=instance_detail&__option_all_attributes=no&__option_over_time_groupby=hour&__option_over_time_groupby_definition=no&__option_over_time_use_graph=yes&__option_most_frequent_groupby=Alert+Instance+Key&__option_most_frequent_use_defs=no&__option_most_frequent_threshhold=50&__option_p1_thres=1&__option_p2_thres=20&__option_p3_p5_thres=50&__exact_Definition+ID=exact&__pattern_Alert+Name=%5BLeRoy%5D&__exact_Alert+Name=substring&__exact_Ecor+Number=exact&__exact_Region+Number=exact&__exact_Machine+IP=exact&__exact_Alert+Instance+Key=exact&__exact_Owner+Email=substring&__exact_Ticket+ID=exact&__exact_AMS+Alert+Definition+ID=exact&__dynamic_filter_=Install+Group&__exact_alert_data_value_1_=exact&__exact_alert_data_value_2_=exact&__exact_alert_data_value_3_=exact&__exact_alert_data_value_4_=exact&gmtoffset=-14400&__time_relation_Age=1&__time_unit_Age=Days&__time_options_=__no_filter_&output_format=HTML&useNewWindow=on&timezone=gmt&datasource=Production&Action=Create%20Report).

### 9\. Modes of Output Promotion

The outputs created by LeRoy can be promoted to the network in the following two ways, facilitated by toggling the “output-promotion-mode” in [dynamic\_config.json](https://git.source.akamai.com/projects/NETOPT/repos/leroy_config/browse/config/dynamic_config.json) from “manual” to “automatic” and vice-versa.

* **Manual promotion**: In this mode, the output is written to a temporary location, the [linked](https://git.source.akamai.com/projects/NETOPT/repos/lr_quota_allocation_outputs_manual/browse) git repository, where can be evaluated before exposing the production network to it.   
  * If the output (maprule assignment and quotas) is identical to what’s in production, or if there is only a minor change to quotas, then there is no strong reason to promote it to production, and the promotion will be skipped.   
  * The change can be considered major if a maprule has been added or removed from a region, or if there is a significant increase or decrease in any maprule’s quota in any region, compared to the current state of production.   
  * This difference will be examined to check if it’s warranted and if it represents any harmful traffic displacement or offload risk. If not, then the output in the temp location would be considered useful to be promoted to production. In this case, a LEROYOPS ticket will be created for the manual promotion of outputs.  
  * The diff in the manual output location and the production will be clearly documented in the ticket. An approval will be sought from the members of the mapping-strategy team and/or the FCS team.   
  * Post approval, the outputs will be manually updated to the git repository ([link](https://git.source.akamai.com/projects/NETOPT/repos/lr_quota_allocation_outputs/browse/fcs.csv)) and the netarch table ([link](https://netarch.akamai.com/s/fd7c9691)) from where FCS and BLC consume fcs.csv and blc.csv, respectively. 

* **Automatic promotion**: in this mode, LeRoy will write its output directly to the [git repository](https://git.source.akamai.com/projects/NETOPT/repos/lr_quota_allocation_outputs/browse/fcs.csv) from and netarch table: netopt.leroy\_maprule\_allocation\_and\_quotas\_for\_blc from where FCS and BLC will respectively consume the outputs. This mode will be enabled only after we have gained sufficient confidence in LeRoy’s input and output validations.

### 10\. Impact Analysis

The main functionality of LeRoy is to decide which maps need to be served from each of the large regions and how much disk space to allocate for each map. Large regions are expected to serve a significant fraction of our traffic. In many tier-0 metros, it is expected to serve more than 30% of the metros' traffic. Any change in maprule allocation could have the following impacts:

* **Adding a region to a maprule’s allowlist.** In the current implementation, BLC adds the large region to the maprule’s primary tier. Once added, the region starts receiving a significant fraction of the metro’s traffic. Since the region’s cache is not pre-warmed with the maprule’s content, we may observe a lot of cache misses and a surge in the midgress traffic. Hence, to contain the midgress spike, LeRoy limits the number of maprule additions or deletions from a region. More details in Section 10.1.

* **Removing a large region from a maprule’s allowlist**. When LeRoy removes a maprule from a large region, the change gets reflected in the maprule’s allow-lists when BLC runs next. BLC runs twice a week on Tuesdays and Thursdays. On removing a maprule, BLC will reallocate it based on the current BLC logic for that maprule. The logic is specialized for each maprule based on its business needs. The logic will determine how many regions will be added to the maprule’s allowlist and at what tier. Note that, since BLC makes changes to the allowlists, the removal of a map and its addition to classic will happen atomically. Hence, we will not have a period when a map is neither in the large region nor in classic. However, once a maprule is removed from the large region, a significant amount of its traffic will be served from classic. Again, since the cache on classic regions could be cold i.e., it may have not served the maprule’s traffic recently, we may incur significant cache misses and observe a spike in midgress traffic. Thus, we limit the number of maprule additions or deletions from a region. More details in Section 10.1.


As LeRoy’s outputs could have a direct impact on how our customer’s traffic is served, it is imperative to thoroughly validate the outputs that LeRoy generates. 

#### 10.1. Output Validation 

* **Check FCS Validation API.** Use the FCS API (described in [link](https://collaborate.akamai.com/confluence/display/MAPENG/FCS+3.3+-+Support+for+Large+Regions+Maprule+Management#FCS3.3SupportforLargeRegionsMapruleManagement-Theversionoffcs.csvstillinproduction\(i.e.thelastgoodonethatFCSsuccessfullyprocessedandpushedout\))) to perform validity checks on the output produced by LeRoy. The primary purpose of the checks run by FCS are to ensure that the changes pushed out downstream by FCS will not cause an error at ghost (e.g. by specifying a quota for a footprint that doesn't exist). It performs the following checks:

  * Disk quotas do not exceed disk size of the region  
  * Correct maprule ids are present in the output

  The API also returns if FCS would block the current quota request. In such a scenario, LeRoy would notify leroy-ops via email of the occurrence and not publish the results until the issue is resolved through an override request. 


* **Refrain from the removal of offload protection.** In every daily run, LeRoy’s output check ensures that for each (large region r, maprule m) pair in the previous daily solution for which a quota exists, as long as the solution of the current daily run keeps region r in map m’s allowlist, the quota for (r,m) is not missing in the output of the current daily run. 

  Not all the maps are given offload targets and quotas (e.g. maps explicitly specified in overrides as those that have no offload targets or quota needs). This refrain does not apply to those maps.   
    
  If this condition fails, i.e. LeRoy’s solution keeps the region r in map m’s allowlist but removes the quota entry for (r,m) from the solution, then LeRoy will revert to the previous quota allocation for the region, and an alert will fire to let leroy-ops know that this condition has occurred. An operator can then file an override request to remedy the situation using the process laid out in Section 5\.   
    
* **Refrain from adding new maps to large regions without any offload protection.** In every daily run, LeRoy’s output check ensures that for each (large region r, maprule m) pair that was not present in the output of the previous daily run, and is newly introduced in the current daily run, a quota is not missing. 

  Not all the maps are given offload targets and quotas (e.g. maps explicitly specified in overrides as those that have no offload targets or quota needs). This refrain does not apply to those maps. 

* **Refrain from demand churn.** By removing or adding maps into a large region, LeRoy creates a churn in the traffic the region is serving. When a new map is added, all requests corresponding to the map would observe cache misses as the cache is not warmed up. This creates performance degradation as we observe a spike in midgress traffic. Further, when a map is removed from the large region, mapping strategy allocates the traffic of the map to other classic regions within the metro. We would like to avoid a large churn in the demand. If LeRoy observes a churn \> X Gbps in any large region for the current run, it notifies leroy-ops and reverts to the previous allocation for that large region. An operator can then file an override request to specify that it is safe to make the change by the process laid out in Section 5\.  
    
* **Refrain from maprule assignment churn.** If LeRoy observes that N or maps are either added or removed from a large region, it notifies leroy-ops and reverts to the previous allocation. An operator can then file an override request to specify that it is safe to make the change by the process laid out in Section 5\.  

#### 10.3. Dependent Systems

The systems that consume LeRoy’s outputs are: 

* **FCS**: LeRoy produces a file fcs.csv that contains disk quotas prescription for each maprule, region pair. This file is uploaded to git in the [linked](https://git.source.akamai.com/projects/NETOPT/repos/lr_quota_allocation_outputs/browse/fcs.csv) location. It is consumed by FCS to create config files fpdata.xml, fpstrategy.xml, and fpindex.xml that reflects LeRoy’s quota prescription. These config files are pushed on to the network via UMP channels and Ghost sets maprule specific disk quotas by parsing the xml files.   
    
  Any changes in the format of fcs.csv will be notified to FCS by filing a Jira ticket under [FPCONTROL](https://track.akamai.com/jira/projects/FPCONTROL/issues/FPCONTROL-314?filter=allopenissues).

* **BLC and Freeflow LP**: LeRoy produces a file blc.csv that contains information about which maprules must be served from which large regions. Further, Leroy produces the table netopt.leroy\_maprule\_allocation\_and\_quotas\_for\_blc for BLC’s consumption. BLC parses this information to update maprule allowlists. The Freeflow LP also consumes LeRoy’s outputs to optimize which classic regions should be added to a maprule’s allowlist given the fact that a fraction of the maprule’s demand in the metro will be served from LRs. 

  Any changes in the format for blc.csv and the schema of the netarch table will be notified to the Mapping Strategy team by filing a Jira ticket under [MAPPINGSTRATEGY](https://track.akamai.com/jira/projects/GSPMAPSTRA/issues/GSPMAPSTRA-4121?filter=allopenissues).

* **LeRoy**. LeRoy itself consumes outputs and inputs of LeRoy’s previous run as inputs for its algorithm