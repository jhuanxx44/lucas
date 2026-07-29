---
title: Microsoft SQL Server
type: concept
industry: 软件服务
as_of: '2026-07-27'
summary: Microsoft SQL Server 是由微软公司推出的关系型数据库解决方案，最新稳定版本为2025版。它最初与Sybase合作开发，后由微软独立研发，支持Windows、Linux和Docker平台。其历史版本众多，功能不断扩展，包括SQL
  CLR、数据压缩、透明数据加密等。
source_ids:
- S1
---

# Microsoft SQL Server

## 概述

Microsoft SQL Server 是由美国微软公司所推出的关联式数据库解决方案，最新的稳定版本是SQL Server 2025，于2024年11月19日发布。[S1] 数据库的内置语言原本采用美国标准局和国际标准组织定义的SQL语言，但微软公司对其进行了部分扩充而成为作业用SQL。[S1] 几个初始版本适用于中小企业的数据库管理，但近年来其应用范围已扩展到大型、跨国企业的数据库管理。[S1]

## 历史渊源

SQL Server 一开始并不是微软自己研发的产品，而是为了与IBM竞争，与Sybase合作所产生的，其最早的发展者是Sybase。[S1] 微软与Sybase合作过SQL Server 4.2版本的研发，微软亦将SQL Server 4.2移植到Windows NT（当时为3.1版）。[S1] 在与Sybase终止合作关系后，微软自力开发出SQL Server 6.0版，往后的SQL Server即均由微软自行研发。[S1] 在与微软终止合作关系后，Sybase在Windows NT上的数据库产品原本称为Sybase SQL Server，后来改为现在的Sybase Adaptive Server Enterprise。[S1]

## 版本演进

SQL Server 的版本演进历史如下：

- 1.0 (OS/2)：1989年，SQL Server 1.0。[S1]
- 4.21 (WinNT)：1993年，SQL Server 4.21。[S1]
- 6.0：1995年，SQL Server 6.0，代号SQL95。[S1]
- 6.5：1996年，SQL Server 6.5，代号Hydra。[S1]
- 7.0：1998年，SQL Server 7.0，代号Sphinx。[S1]
- 8.0：2000年，SQL Server 2000，代号Shiloh，内部版本号539。[S1]
- 8.0：2003年，SQL Server 2000 64-bit版本，代号Liberty，版本号539。[S1]
- 9.0：2005年，SQL Server 2005，代号Yukon，版本号611/612。[S1]
- 10.0：2008年，SQL Server 2008，代号Katmai，版本号655。[S1]
- 10.25：2009年，SQL Azure，代号CloudDatabase。[S1]
- 10.50：2010年，SQL Server 2008 R2，代号Kilimanjaro，版本号661。[S1]
- 11.0：2012年，SQL Server 2012，代号Denali，版本号706。[S1]
- 12.0：2014年，SQL Server 2014，版本号782。[S1]
- 13.0：2016年，SQL Server 2016，版本号852，于2016年6月1日发布。[S1]
- 14.0：2017年，SQL Server 2017，代号Helsinki，版本号869，于2017年10月2日发布。[S1]
- 15.0：2019年，SQL Server 2019，代号Seattle，版本号895，于2019年11月4日发布。[S1]
- 16.0：2022年，SQL Server 2022，代号Dallas，于2022年11月16日发布，RTM版本为16.0.1000.6。[S1]
- 2025：2024年11月19日，微软发布SQL Server 2025，称为Enterprise AI-ready database from ground to cloud。[S1]

### 早期版本重要事件

SQL Server 1.0 & 1.1：1986年微软与Sybase合作，1989年上市Ashton-Tate/Microsoft SQL Server 1.0。1990年微软终止与Ashton-Tate的合约，推出Microsoft SQL Server 1.1。[S1] 1991年起微软获得Sybase授权可以检视与修改SQL Server的原始程式码。但销售不佳。[S1]

SQL Server 4.2：1992年由Sybase与微软共同发表，微软贡献了将核心程式码移植到OS/2、提供客户端函式库、开发部分管理工具。但最初是16位元为基础。[S1]

SQL Server for Windows NT：1993年Windows NT 3.1出货后30天，完成SQL Server for Windows NT（4.2）的开发工作。这是第一个Windows NT上的SQL Server。[S1]

SQL Server 6.0：1994年4月12日微软与Sybase正式终止合作关系，微软获得对SQL Server程式码的完全控制权。SQL Server 6.0（SQL 95）于1995年6月14日RTM，是完全由微软自行开发的版本。[S1] SQL Server 6.5于1996年发布。[S1]

SQL Server 7.0：1998年12月RTM。核心重新撰写，引入了OLE DB和MSDE等技术。[S1]

SQL Server 2000：2000年8月9日RTM，生命期最长（至2005年11月），后续添加了Notification Services、Reporting Services、Web Administration、XML（SQLXML）等功能，也是第一个出现在Windows CE上的SQL Server。[S1]

SQL Server 2005：代号Yukon，于2005年11月与Visual Studio 2005一起发表。新功能包括SQL Server Management Studio（SSMS）、Business Intelligence Development Studio（BIDS）、新增多种Transact-SQL指令、原生XML数据类型、SQL CLR、SQL Server Integration Services等。[S1]

SQL Server 2008：2008年8月6日发表，代号Katmai。新功能包括基于原则的管理基础架构、资源调节器、资料压缩、透明数据加密、FILESTREAM数据类型、空间数据类型等。[S1]

SQL Server 2008 R2：2010年4月21日正式发表。[S1]

SQL Server 2012：2012年3月6日正式发表，提供标准、企业、智慧商务三种版本。[S1]

SQL Server 2014：2014年4月1日正式发表。[S1]

SQL Server 2016：2016年6月1日发布。[S1]

SQL Server 2017：2017年10月2日发布。同时，SQL Server on Linux作为多操作系统版本发布，支持Linux平台。[S1]

SQL Server 2022：2022年11月16日发布。从SQL Server 2022开始，R、Python和JAVA的执行阶段将不再随SQL安装程式一起安装。[S1]

## 对编程的支持

SQL Server 支持多种编程方式：
- 以T-SQL语法写SQL预存程序或SQL预存函数。[S1]
- 支持ODBC及OLE DB。[S1] SQL Server Native Client是原生客户端组件，但在SQL Server 2012起废除。[S1]
- 自SQL Server 2005以后，以SQL CLR支持使用C#或VB.NET撰写外挂的DLL档来扩充功能。[S1]
- 以sqlcmd提供在批次档执行SQL命令的功能。[S1]
- 在ASP，可经ADO存取SQL Server；在ASP.NET，可经ADO.NET存取。[S1]
- 在Java或JSP，可经JDBC存取；在PHP，可经PDO存取。[S1]

## 版本分类

SQL Server 依功能分成不同版本：
- Enterprise Edition：大型企业及大型数据库或数据仓储的服务器版本。[S1]
- Standard Edition：一般企业的服务器版本。[S1]
- Workgroup Edition：自SQL Server 2000开始，专为工作群组或部门设计。[S1]
- Web Edition：自SQL Server 2008开始，专为Web服务器与Web Hosting设计。[S1]
- Express Edition：免费版本，适用于小型应用，功能有限制，如只能使用一颗处理器、最大数据库大小4GB等。[S1]
- Compact Edition：免费版本，专用于行动装置及Windows CE操作系统。[S1]
- Developer Edition：与Enterprise Edition功能相同，但只授权开发与测试，价格极低。[S1]

## 架构与服务

（注：来源快照中“架构”和“服务”小节仅有标题而无具体内容，因此无法提供详细信息。）[S1]

## 资料库管理工具

- SQL Server Management Studio (SSMS)：需另外安装的GUI管理工具，绝大多数功能可由SSMS完成。[S1]
- Navicat for SQL Server：专为Microsoft SQL Server设计的强大数据库管理及开发工具，支持大部分SQL Server功能。[S1]

## 来源

- [S1] Microsoft SQL Server - 维基百科，自由的百科全书 — https://zh.wikipedia.org/wiki/Microsoft_SQL_Server（抓取日期：2026-07-27）
