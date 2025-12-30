## Cluster Regions and Their Roles

This CockroachDB deployment is organized into **purpose-driven regions**, each designed to isolate a distinct workload class at both the infrastructure and database layers. Regions differ intentionally in **data locality, resource envelopes, access patterns, and failure tolerance**.

---

## Transactional Regions (`tx1`, `tx2`, `tx3`)

**Purpose**
Transactional (TX) regions handle **hot, latency-sensitive, business-critical workloads**. These regions serve day-to-day application traffic.

**Characteristics**

* Multiple regions for availability and load distribution
* Each region consists of **three CockroachDB nodes**
* Nodes are **small and tightly bounded** in CPU and memory
* Optimized for:

  * low-latency reads and writes
  * high concurrency
  * predictable performance

**Architectural intent**

* TX regions prioritize **correctness and availability**
* They are structurally protected from analytical and long-running workloads
* Cross-region redundancy ensures continued business operation if one TX region degrades

---

## Reporting Region (`report`)

**Purpose**
The reporting region serves **heavy analytical and reporting workloads**, including large scans, aggregations, and vector search workloads.

**Characteristics**

* A **dedicated region** with its own CockroachDB nodes
* Backed by **large EC2 instances** with substantial CPU and memory
* Nodes reserve nearly the entire host, ensuring exclusivity
* Designed to run:

  * OLAP queries
  * wide scans
  * compute-intensive analytics
  * vector search indexes and queries

**Architectural intent**

* Reporting workloads are **structurally isolated** from TX traffic
* Resource-hungry queries cannot interfere with transactional performance
* The region behaves like a “big iron” analytics tier
* Multiple nodes provide **viable resilience** within the region

---

## Archive Region (`archive`)

**Purpose**
The archive region holds **historical / cold data** that is no longer part of the hot transactional path but must remain queryable and correct.

**Characteristics**

* Single logical region with **multiple moderately sized nodes**
* Resource profile sits **between TX and report**
* Designed for:

  * infrequent access
  * long timeline scans
  * compliance, audit, or historical analysis
* Workloads are expected to be:

  * low-priority
  * read-mostly
  * tolerant of higher latency

**Architectural intent**

* Archive isolates cold data so it does not consume TX or reporting resources
* Durability and correctness matter more than availability
* Failure of the archive region does **not** block core business operations
* The region enforces lifecycle separation rather than uptime guarantees

---

## Region-Specific Entry Points (HAProxy)

Each region is fronted by its own HAProxy instance, providing:

* **Explicit routing** to the intended region
* Clear separation of access paths
* The ability to reason about workload placement and isolation at the edge

HAProxy does not terminate TLS or transform traffic; it enforces **routing intent**, not policy.

---

## Summary View

| Region  | Primary Role           | Workload Type | Resource Profile | Availability Expectation |
| ------- | ---------------------- | ------------- | ---------------- | ------------------------ |
| TX      | Business transactions  | OLTP          | Small, many      | High                     |
| Report  | Analytics & vectors    | OLAP          | Large, exclusive | Medium–High              |
| Archive | Historical / cold data | Read-mostly   | Moderate         | Low–Medium               |

---

**Key takeaway**
This architecture demonstrates that workload isolation is achieved not through query hints or operational discipline, but through **explicit regional intent combined with resource-enforced boundaries**, making isolation visible, enforceable, and economically rational.
