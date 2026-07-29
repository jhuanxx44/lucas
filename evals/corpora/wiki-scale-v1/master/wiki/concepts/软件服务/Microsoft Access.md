---
title: Microsoft Access
type: concept
industry: 软件服务
as_of: '2026-07-27'
summary: Microsoft Access是微软发布的关联式数据库管理系统，结合Microsoft Jet Database Engine和图形用户界面，是Microsoft
  Office的系统程序之一。它能够存取多种数据库，常用于小型企业、大公司部门和开发人员制作数据处理系统，但可扩展性不高。
source_ids:
- S1
---

# Microsoft Access

## 概述

**Microsoft Office Access**（前名 **Microsoft Access**）是由 微软 发布的 关联式资料库管理系统。它结合了 Microsoft Jet Database Engine 和 图形用户界面 两项特点，是 Microsoft Office 的系统程式之一。[S1]

Access能够存取Access/Jet、 Microsoft SQL Server、 Oracle数据库，或者任何 ODBC 相容 资料库 内的资料。虽然它支持部分 物件导向 技术，但是未能成为一种完整的物件导向开发工具。[S1]

其实Access也是微软公司另一个通讯程式的名字，想与 ProComm 以及其他类似程式来竞争。可是事后微软证实这是个失败计划，并且将它中止。数年后他们把名字重新命名于此数据库软体。[S1]

## 历史

Microsoft Access 1.0发布于1992年11月，当时该软体以7张1.44 MB 磁片 形式发售。[S1]

为了配合Word的版本号码，Access版本号自Office 95开始与Word同步，版本号配合Word 7订为7.0。[S1]

Access 2007起资料库改以新档案格式`.accdb`储存。由于与旧Access版本不相容，若需在较旧的Access版本里读取，需要先转存回`.mdb`。[S1]

Access 2013起已不再支援 dBase 资料库，无法汇入`.dbase`的资料库档案。[S1]

由于Office 2024不再提供Professional版本，故Access不再于零售卖断的Microsoft Office版本中出现；但Microsoft 365订阅版本中仍设有Access。[S1]

版本历史表（部分）：[S1]

| 年份 | 版本 | 版本代号 | 作业系统需求 | 对应的 Office 版本 |
| --- | --- | --- | --- | --- |
| 1992年 | Access 1.1 | 1 | Windows 3.0 |  | [S1]
| 1993年 | Access 2.0 | 2.0 | Windows 3.1x | Office 4.3 Pro | [S1]
| 1995年 | Access for Windows 95 | 7.0 | Windows 95 | Office 95 Professional | [S1]
| 1997年 | Access 97 | 8.0 | Windows 9x、NT 3.51/4.0 | Office 97 Professional、Developer | [S1]
| 1999年 | Access 2000 | 9.0 | Windows 9x、NT 4.0、2000 | Office 2000 Professional、Premium及Developer | [S1]
| 2001年 | Access 2002 | 10 | Windows 98 以上 | Office XP Professional及Developer | [S1]
| 2003年 | Access 2003 | 11 | Windows 2000 以上 | Office 2003 Professional及Professional Enterprise | [S1]
| 2007年 | Microsoft Office Access 2007 | 12 | Windows XP SP2 | Office 2007 Professional、Professional Plus、Ultimate及Enterprise | [S1]
| 2010年 | Microsoft Office Access 2010 | 14 | Windows XP SP3、 Vista SP1、 Windows 7 | Office 2010 Professional、Professional Academic及Professional Plus | [S1]
| 2012年 | Microsoft Office Access 2013 | 15 | Windows Server 2008 R2、 Windows 7 | Office 2013 Professional及Professional Plus | [S1]
| 2015年 | Microsoft Office Access 2016 | 16 | Windows 7 | Office 2016 Professional及Professional Plus | [S1]
| 2018年 | Microsoft Office Access 2019 |  | Windows 10 | Office 2019 Professional及Professional Plus | [S1]
| 2021年 | Microsoft Office Access 2021 |  | Windows 10、 Windows 11 | Office 2021 Professional及Professional Plus | [S1]

## 用途

Microsoft Access在很多地方得到广泛使用，例如小型企业，大公司的部门。喜爱编程的开发人员亦利用它来制作处理数据的桌面系统。它也常被用来开发简单的WEB应用程式。[S1]

它的使用方便程度和强大的设计工具为初级程式员提供许多功能。不过，方便性的宣传，常令人误解。在过于乐观的误导下，让许多没有程式设计背景的办公室从业人员应用此软体，并以为能够创造可用的系统，但此工具本身的局限性，常常使这些使用者失败。[S1]

一些专业的应用程式开发人员使用Access内附的 快速应用开发 功能，特别是给街道上的推销员制作一个 初型 或独立应用程式的工具。可是如果是透过网路存取 数据 的话，Access的 可扩放性 并不高．因此当程式被较多使用者使用时，他们的选择多会是倾向于一些 客户端-伺服器 为本的方案，例如 Oracle、 IBM DB2、 Microsoft SQL Server、 Windows SharePoint Services、 PostgreSQL、 MySQL、 Alpha Five、 MaxDB，或者 Filemaker。无论如何，不少Access的功能（表单，报告，序列和 VB代码）可以用作其他数据库的后期应用，包括JET（档案为主的数据库引擎，Access预设使用）、 Microsoft SQL Server、 Oracle 和任何其他跟 ODBC 相容的产品。这种方法允许开发者把一个成熟的应用的数据移动到一台更大功率的伺服器而不会在适当的位置牺牲发展。[S1]

## SQL

Access查询中使用的默认使用“Microsoft Jet SQL”，而 ADO 中使用的SQL语法是“ANSI SQL”。这两种语法存在轻微的差别（中间还包含某些特殊函数和功能）并非完全兼容。其中通配符就不一样：对于多个字符，前者是`*`而后者是`%`；对于单个字符，前者是`?`而后者是`_`。Jet SQL基本遵从了SQL ANSI-89 Level 1。对于Access的字段类型为`True`/`False`，在SQL语句中可用`0`对应`False`，`-1`对应`True`。不能用`1`对应`True`。[S1]

也可以将Access数据库查询的语法设置为兼容ANSI SQL（在Access选项那里设置），但是这样做的话，编写SQL语句就要遵循ANSI SQL语法规则了。对于之前已经使用过的Access数据库不建议这样做，因为很可能会导致原有编写的SQL查询失效，进而造成诸多不便。[S1]

Access使用的Jet SQL引擎，每次只能执行一条SQL语句。如果成批执行多条SQL语句，需要使用 Visual Basic for Applications 编程。在Access的VBA中执行SQL语句，有三种方法。[S1]

- `DoCmd.RunSQL`：基于Access的对象模型，使用Microsoft Jet SQL，在SQL语句中可以使用VBA函数。需要在调用前设置`DoCmd.SetWarnings False`关闭提示或确认对话框。执行时在Access状态栏显示进度条，可通过Esc键中止执行。不能获取SQL语句影响的记录行数。不能将多个SQL语句的执行放在同一事务中。[S1]
- `CurrentDB.Execute`：基于 DAO 对象模型，使用Microsoft Jet SQL，在SQL语句中可以使用VBA函数。没有提示或确认对话框的显示。执行时没有在Access状态栏显示进度条，不可以通过Esc键中止执行。能获取SQL语句影响的记录行数。可以将多个SQL语句的执行放在同一事务中。[S1]
- `CurrentProject.Connection.Execute`：基于 ADO 对象模型，连接到不同数据库使用不同的SQL语法。对Access使用ISO SQL标准语法并可以使用VBA函数。没有提示或确认对话框的显示。执行时没有在Access状态栏显示进度条，不可以通过Esc键中止执行。能获取SQL语句影响的记录行数。可以将多个SQL语句的执行放在同一事务中。[S1]

例如：[S1]

```
Dim strSQL As String
strSQL = "SELECT * INTO [excel 8.0;database=d:\gz.xls].sheet1 FROM table1 WHERE table1.city = 'gz' " [S1]
 :REM 执行该函数进行SQL查询
CurrentProject.Connection.Execute strSQL
```

## 编程模型

Access软件自身提供了一套 COM 对象体系，可供其它软件（如Excel）使用 VBA 或者 C#、 C++ 等编程语言调用Access的功能。[S1]

- Application：Access应用程序环境
- DBEngine：数据库管理系统
- Debug：立即窗口对象，可用Print输出文本
- Forms：包含所有打开的窗口
- Reports：包含所有打开的报表
- Screen：屏幕
- DoCmd[S1]

## 来源

- [S1] Microsoft Access - 维基百科，自由的百科全书 — https://zh.wikipedia.org/wiki/Microsoft_Access（抓取日期：2026-07-27）
