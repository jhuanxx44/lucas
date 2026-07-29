---
title: Hadoop
type: concept
industry: 云计算
as_of: '2026-07-27'
summary: Apache Hadoop是一个开源软件框架，用于大数据分布式存储与处理，基于MapReduce计算模型和HDFS文件系统，灵感源于Google的MapReduce和GFS论文。它由Apache软件基金会开发，采用Java编写，支持跨平台运行，最初发布于2006年4月1日。
source_ids:
- S1
---

# Hadoop

## 概述

Apache Hadoop 是一款支持数据密集型分布式应用的开源软件框架，以 Apache 2.0 许可协议发布，有助于使用许多计算机组成的网络来解决数据、计算密集型的问题 [S1]。基于 MapReduce 计算模型，它为大数据 的分布式存储与处理提供了一个软件框架。所有的 Hadoop 模块都有一个基本假设，即硬件故障是常见情况，应该由框架自动处理 [S1]。

Hadoop 框架本身主要是用 Java 编程语言编写的，也包括了一些 C 语言编写的本机代码和 Shell 脚本编写的命令行实用程序 [S1]。尽管 MapReduce Java 代码很常见，但任何编程语言都可以与 Hadoop Streaming 一起使用来实现用户程序的 map 和 reduce 部分 [S1]。

## 核心模块

Apache Hadoop 框架由以下基本模块构成 [S1]：

- **Hadoop Common** – 包含了其他 Hadoop 模块所需的库和实用程序；
- **Hadoop Distributed File System (HDFS)** – 一种将数据存储在集群中多个节点中的分布式文件系统，能够提供很高的带宽；
- **Hadoop YARN** – （于 2012 年引入）一个负责管理集群中计算资源，并实现用户程序调度的平台 [S1]；
- **Hadoop MapReduce** – 用于大规模数据处理的 MapReduce 计算模型实现；
- **Hadoop Ozone** – （于 2020 年引入）Hadoop 的对象存储。 [S1]

Hadoop 一词通常代指其基本模块和子模块以及生态系统，或可以安装在 Hadoop 之上的软件包的集合，例如 Apache Pig、Apache Hive、Apache HBase、Apache Phoenix、Apache Spark、Apache ZooKeeper、Cloudera Impala、Apache Flume、Apache Sqoop、Apache Oozie 和 Apache Storm [S1]。

Apache Hadoop 的 MapReduce 和 HDFS 模块的灵感来源于 Google 的 MapReduce 和 Google File System 论文 [S1]。

## 历史与版本

Hadoop 由 Doug Cutting 和 Mike Cafarella 原创，由 Apache 软件基金会开发 [S1]。首次发布于 2006 年 4 月 1 日 [S1]。当前稳定版本为 3.4.2，于 2025 年 8 月 29 日发布 [S1]。

## 主要子项目与相关项目

### 主要子项目

- Hadoop Common：在 0.20 及以前的版本中，包含 HDFS、MapReduce 和其他项目公共内容，从 0.21 开始 HDFS 和 MapReduce 被分离为独立的子项目，其余内容为 Hadoop Common [S1]。
- HDFS：Hadoop 分布式文件系统 [S1]。
- MapReduce：并行计算框架，0.20 前使用 org.apache.hadoop.mapred 旧接口，0.20 版本开始引入 org.apache.hadoop.mapreduce 的新 API [S1]。

### 相关项目

- Apache HBase：分布式 NoSQL 列数据库，类似谷歌公司 BigTable [S1]。
- Apache Hive：构建于 Hadoop 之上的数据仓库，通过一种类 SQL 语言 HiveQL 为用户提供数据的归纳、查询和分析等功能。Hive 最初由 Facebook 贡献 [S1]。
- Apache Mahout：机器学习算法软件包 [S1]。
- Apache Sqoop：结构化数据（如关系数据库）与 Apache Hadoop 之间的数据转换工具 [S1]。
- Apache ZooKeeper：分布式锁设施，提供类似 Google Chubby 的功能，由 Facebook 贡献 [S1]。
- Apache Avro：新的数据序列化格式与传输工具，将逐步取代 Hadoop 原有的 IPC 机制 [S1]。

## 知名用户

### Hadoop 在 Yahoo! 的应用

2008 年 2 月 19 日，雅虎使用 10,000 个微处理器核心的 Linux 计算机集群运行一个 Hadoop 应用程序 [S1]。

### 其他用户

其他知名用户包括：A9.com、Facebook、Fox Interactive Media、华为、IBM、ImageShack、资讯科学研究院、Joost、Last.fm、Powerset、纽约时报、Rackspace、Veoh、中华电信、中国移动 [S1]。

## 与其他系统的集成

### Hadoop 与 Sun Grid Engine

升阳电脑的 Sun Grid Engine 可以用来调度 Hadoop Job [S1]。

### Hadoop 与 Condor

威斯康辛大学麦迪逊分校的 Condor 计算机集群软件也可以用作 Hadoop Job 的排程 [S1]。

## 参见

- 大数据
- 云端运算
- 高性能计算集群
- OpenStack－以 Apache 许可证授权的云端运算软件
- Apache Spark

（以上内容均基于来源 [S1]）

## 来源

- [S1] Apache Hadoop - 维基百科，自由的百科全书 — https://zh.wikipedia.org/wiki/Hadoop（抓取日期：2026-07-27）
