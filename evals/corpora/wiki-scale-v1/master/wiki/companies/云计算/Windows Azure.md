---
title: Windows Azure
type: company
industry: 云计算
as_of: '2026-07-27'
summary: Microsoft Azure 是微软的公有云服务平台，自2008年开发，2010年2月正式推出，提供超过30种服务，全球有54座数据中心和44个CDN节点。该平台经历了从PaaS到IaaS的扩展，2014年更名为Microsoft
  Azure以体现多平台支持，并持续增加新功能和服务。
source_ids:
- S1
---

# Windows Azure

## 概述

Microsoft Azure 是微软的公用云端服务平台，是微软线上服务的一部分，自2008年开始发展，2010年2月份正式推出，目前全球有54座资料中心以及44个CDN跳跃点（POP），并且于2015年时被Gartner列为云端运算的领先者[S1]。目前Microsoft Azure已包含30余种服务，数百项功能，并且为微软带来了12亿美元的获利（2015年度）[S1]。Microsoft Azure为北美3大云端服务提供者（CSP）之一[S1]。

## 发展历程

Microsoft Azure的发展最早源于2006年，由Amitabh Srivastava与Dave Culter主导，代号为Red Dog，旨在开发运算资源管理工具、分散式管理系统、高可用储存系统及支援平台[S1]。2010年2月推出公开服务版，当时名为Azure Service Platform，包含Cloud Service、Storage、SQL Azure与AppFabric，仅提供PaaS[S1]。2010年下半年新增VM Role和Azure Connect[S1]。2012年更新管理介面为HTML5，首次发行IaaS（虚拟机器与虚拟网路），发行Website服务并支援.NET以外平台，以及Media Service[S1]。2013-2014年加入Hadoop（HDInsight）、Streaming Analytics、Data Factory、Event Hub、Machine Learning等大数据服务，并更新SQL Azure[S1]。2014年微软将Windows Azure更名为Microsoft Azure，以修正市场方向，表明不仅支援Windows[S1]。2015年合并Website与Mobile Service为App Services，推出Redis Cache、Application Insights、DNS、Search等[S1]。2016年推出Azure Functions（无伺服器）和Service Fabric（微服务）[S1]。2022年12月，微软宣布禁止用户使用Azure进行数位货币挖矿[S1]。

## 基础建设

Microsoft Azure是专为微软资料中心管理的特殊版本Windows Server，具有自我管理机能，能自动监控伺服器与储存资源、更新修补程式、执行虚拟机器部署与镜像备份，并与中控软体Fabric Controller沟通[S1]。Fabric Controller管理所有实体伺服器，包含Azure Guest OS部署、Hotfix修补、机器状态回报及VM影像复制，本身具有高可用性[S1]。RDFE（Red Dog's Front-End）是Azure前端介面，对外接受REST API命令，对内配置资源，包含Fault Domain和Upgrade Domain的计算[S1]。网路基础建设早期使用DLA架构，2012年起改用Quantum10（基于Clos网路拓朴），提供更高频宽与备援[S1]。后续发展包括Azure SmartNIC（FPGA辅助）、Virtual Filtering Platform、Switch Abstraction Interface（SAI）、Azure Cloud Switch等[S1]。

## 服务位置

Microsoft Azure全球有54个资料中心（另有6个兴建中）及44个CDN跳跃点[S1]。服务区域分为三种：Azure Cloud（全球54个据点，如美国、欧洲、亚洲、大洋洲、南美洲、非洲）、Azure China（中国大陆，由世纪互联与中国电信经营）、Azure Government Cloud（美国政府专用，6座资料中心）[S1]。具体地区包括美国多个区域、加拿大、欧洲（爱尔兰、荷兰、德国、英国、法国）、亚洲（香港、新加坡、日本、印度、中国、韩国）、大洋洲（澳大利亚）、南美洲（巴西）、非洲（南非）等[S1]。

## 管理模式

早期使用服务管理模式（ASM），以服务为主体。2014年提出资源管理模式（ARM），以资源为观点，允许使用资源群组组织资源，适用于中大型应用[S1]。ARM由Azure Ibiza Portal、Azure PowerShell v1.0、Azure CLI v1.0支援，并引入资源范本（Resource Template）[S1]。

## 服务

Microsoft Azure包含30余种服务，主要分类如下[S1]：

- **运算服务**：IaaS包括Virtual Machine（支援Windows和Linux）和RemoteApp；PaaS包括Cloud Service、Service Fabric、Azure Kubernetes Service（AKS）、Web Apps、Logic Apps、Functions等[S1]。
- **应用服务**：Azure App Service（合并Website和Mobile Service）、API App、Logic App；AppFabric提供Access Control Service和Service Bus，后加入Notification Hub[S1]。
- **储存服务**：Azure Storage（Blob、Table、Queue、File）；SQL Azure（后更名Azure SQL Database，支援MySQL和PostgreSQL）；Azure Search；Azure Redis Cache；Azure Cosmos DB（多模型NoSQL）[S1]。
- **分析服务**：Azure Event Hub、Data Factory、Stream Analytics、HDInsight（Hadoop）、Machine Learning、Data Lake[S1]。
- **网路服务**：虚拟网路、ExpressRoute、Traffic Manager、名称代管服务[S1]。
- **身分识别与存取管理**：Microsoft Entra ID（原Azure AD），支援多重要素验证、Azure AD B2C、Azure AD Domain Services[S1]。
- **开发人员服务**：Application Insights、Azure DevOps、Azure App Center[S1]。
- **管理服务**：Scheduler、Automation、Operational Insights、KeyVault、Security Center、Backup、Site Recovery[S1]。

## 法规与规范认证

Microsoft Azure已通过数十项法规与规范认证，包括政府机关（如阿根廷个人资料保护法、美国CJIS、FedRAMP、HIPAA等）和产业标准（如ISO 27001、ISO 27018、PCI-DSS Level 1 v3.0等）[S1]。

## 工具

管理与存取Microsoft Azure的工具包括：Microsoft Visual Studio（配合Azure SDK for .NET）、Azure PowerShell、Azure CLI、Azure服务管理REST APIs、System Center App Controller、Azure Storage Explorer（社群开发）及Microsoft Storage Explorer（官方开发）[S1]。

## 来源

- [S1] Microsoft Azure - Wikipedia — https://zh.wikipedia.org/wiki/Windows_Azure（抓取日期：2026-07-27）
