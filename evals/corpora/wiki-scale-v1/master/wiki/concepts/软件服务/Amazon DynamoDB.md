---
title: Amazon DynamoDB
type: concept
industry: 软件服务
as_of: '2026-07-27'
summary: Amazon DynamoDB是亚马逊提供的NoSQL数据库服务，支持键-值存储和文档型数据结构，于2012年1月发布。它采用同步复制策略以保证高持久性和可用性，是Amazon
  SimpleDB的演进产品。
source_ids:
- S1
---

# Amazon DynamoDB

## 概述

**Amazon DynamoDB** 是一个支持 键-值存储 和 文档型 数据结构的 NoSQL 数据库 服务，是 亚马逊云计算服务 的一部分。[S1] DynamoDB的数据模式类似Dynamo（存储系统），不过底层实现有所不同。[S1]

## 主要特性

Dynamo具有多主（multi-master）的设计，要求从机（client）解决版本冲突，而DynamoDB采取数据库同步复制（synchronous replication）的策略，以达到更高的数据持续性和可用性。[S1] 该服务的类型为面向文档的数据库和键-值存储，采用专有许可协议，支持跨平台操作系统，界面语言为英语。[S1]

## 历史

Amazon DynamoDB最初由亚马逊首席技术官Werner Vogels于2012年1月18日发布，作为当时 Amazon SimpleDB 的演进产品。[S1] 首次发布距今14年（截至2012年1月）。[S1] 开发者是亚马逊公司，官方网址为 aws.amazon.com/dynamodb/。[S1]

## 来源

- [S1] Amazon DynamoDB - 维基百科，自由的百科全书 — https://zh.wikipedia.org/wiki/Amazon_DynamoDB（抓取日期：2026-07-27）
