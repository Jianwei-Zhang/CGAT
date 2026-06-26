-- phpMyAdmin SQL Dump
-- version 4.1.13
-- http://www.phpmyadmin.net
--
-- Host: localhost
-- Generation Time: May 13, 2015 at 11:32 AM
-- Server version: 5.1.73
-- PHP Version: 5.3.3

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8 */;

--
-- Database: `lims`
--

-- --------------------------------------------------------

--
-- Table structure for table `alignment`
--

CREATE TABLE IF NOT EXISTS `alignment` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `program` varchar(255) COLLATE utf8_unicode_ci NOT NULL,
  `query` bigint(20) NOT NULL,
  `subject` bigint(20) NOT NULL,
  `perc_indentity` decimal(5,2) DEFAULT NULL,
  `align_length` int(11) DEFAULT NULL,
  `mismatches` int(5) DEFAULT NULL,
  `gaps` int(5) DEFAULT NULL,
  `q_start` int(10) DEFAULT NULL,
  `q_end` int(10) DEFAULT NULL,
  `s_start` int(10) DEFAULT NULL,
  `s_end` int(10) DEFAULT NULL,
  `e_val` varchar(10) COLLATE utf8_unicode_ci DEFAULT NULL,
  `bit_score` varchar(10) COLLATE utf8_unicode_ci DEFAULT NULL,
  `hidden` tinyint(1) NOT NULL DEFAULT '0',
  PRIMARY KEY (`id`),
  KEY `query` (`query`),
  KEY `subject` (`subject`),
  KEY `qs` (`query`,`subject`)
) ENGINE=MyISAM  DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci;

-- --------------------------------------------------------

--
-- Table structure for table `clones`
--

CREATE TABLE IF NOT EXISTS `clones` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(16) COLLATE utf8_unicode_ci NOT NULL,
  `libraryId` int(10) NOT NULL,
  `plate` varchar(4) COLLATE utf8_unicode_ci NOT NULL,
  `well` varchar(3) COLLATE utf8_unicode_ci NOT NULL,
  `origin` varchar(16) COLLATE utf8_unicode_ci NOT NULL,
  `sequenced` tinyint(1) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`),
  KEY `origin` (`origin`),
  KEY `libraryId` (`libraryId`)
) ENGINE=MyISAM  DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci;

-- --------------------------------------------------------

--
-- Table structure for table `link`
--

CREATE TABLE IF NOT EXISTS `link` (
  `parent` int(10) NOT NULL,
  `child` varchar(16) NOT NULL,
  `type` varchar(16) NOT NULL,
  KEY `parent` (`parent`),
  KEY `child` (`child`),
  KEY `type` (`type`)
) ENGINE=MyISAM DEFAULT CHARSET=latin1;

-- --------------------------------------------------------

--
-- Table structure for table `matrix`
--

CREATE TABLE IF NOT EXISTS `matrix` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `container` varchar(16) NOT NULL,
  `name` varchar(32) NOT NULL,
  `o` int(10) unsigned NOT NULL,
  `x` int(10) unsigned NOT NULL DEFAULT '0',
  `y` int(10) unsigned NOT NULL DEFAULT '0',
  `z` int(10) unsigned NOT NULL DEFAULT '0',
  `barcode` int(10) NOT NULL,
  `note` longtext,
  `creator` varchar(45) NOT NULL,
  `creationDate` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `name` (`name`),
  KEY `o` (`o`),
  KEY `x` (`x`),
  KEY `y` (`y`),
  KEY `z` (`z`),
  KEY `barcode` (`barcode`),
  FULLTEXT KEY `note` (`note`)
) ENGINE=MyISAM  DEFAULT CHARSET=latin1;

--
-- Table structure for table `config`
--

CREATE TABLE IF NOT EXISTS `config` (
  `id` int(5) unsigned NOT NULL AUTO_INCREMENT,
  `type` varchar(25) COLLATE utf8_unicode_ci NOT NULL,
  `fieldName` varchar(255) COLLATE utf8_unicode_ci NOT NULL,
  `fieldDefault` varchar(255) COLLATE utf8_unicode_ci NOT NULL,
  `fieldValue` varchar(255) COLLATE utf8_unicode_ci NOT NULL,
  `fieldDescription` text COLLATE utf8_unicode_ci NOT NULL,
  `weight` tinyint(4) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=MyISAM  DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci AUTO_INCREMENT=66 ;

--
-- Dumping data for table `config`
--

INSERT INTO `config` (`id`, `type`, `fieldName`, `fieldDefault`, `fieldValue`, `fieldDescription`, `weight`) VALUES
(1, 'Site', 'SITENAME', 'text::LIMS', 'Laboratory Information Management System (Beta)', 'Site name', 0),
(2, 'Site', 'COPYRIGHT', 'textarea::2011 AGI. All rights reserved.', '2011-2016 AGI. All rights reserved.', 'Copyright information', 5),
(3, 'Site', 'KEYWORDS', 'textarea::arizona, genomics, institute', 'arizona, genomics, institute', 'Keywords', 4),
(4, 'Display', 'recentProjectsPerPage', 'number:5,10,15,20,25,30:10', '10', 'Number of recent projects per page', 1),
(5, 'Display', 'recentPipelinesPerPage', 'number:5,10,15,20:10', '10', 'Number of recent pipelines per page', 2),
(6, 'Display', 'recentFilesPerPage', 'number:5,10,15,20:20', '20', 'Number of recent files per page', 3),
(7, 'Display', 'projectsPerPage', 'number:5,10,15,20,25,30:10', '10', 'Number of projects per page', 5),
(8, 'Display', 'recentProcessesPerPage', 'number:5,10,15,20,25,30:5', '20', 'Number of recent processes per page', 4),
(9, 'Display', 'pipelinesPerPage', 'number:5,10,15,20,25,30:10', '10', 'Number of pipelines per page', 6),
(10, 'Display', 'filesPerPage', 'number:5,10,15,20,25,30:20', '20', 'Number of files per page', 7),
(11, 'Display', 'processesPerPage', 'number:5,10,15,20,25,30:10', '10', 'Number of processes per page', 8),
(12, 'Path', 'copyDestination', 'text::/wing2/users/SHARED', '/wing2/users/SHARED', 'Default destination directory for copying files to', 0),
(13, 'Path', 'copyFrom', 'text::/wing2/users/SHARED', '/wing2/users/SHARED', 'Default directory for copying files from', 0),
(14, 'Display', 'popularPrograms', 'programs::', '1,2,3', 'Popular programs', 0),
(15, 'Display', 'favoritePrograms', 'programs::', '', 'Favorite programs', 0),
(16, 'Display', 'maxSearchHits', 'number:5,7,10:5', '5', 'Maximum search hits', 10),
(17, 'Profile', 'DoB', 'date::', '', 'Date of birth', 3),
(18, 'Profile', 'street', 'text::1657 E. Helen Street', '1657 E. Helen Street', 'Street', 4),
(19, 'Profile', 'city', 'text::Tucson', 'Tucson', 'City', 5),
(20, 'Profile', 'state', 'text::AZ', 'AZ', 'State', 6),
(21, 'Profile', 'zipcode', 'text::85719', '85719', 'Zip code', 7),
(22, 'Profile', 'country', 'text::USA', 'USA', 'Country', 8),
(23, 'Site', 'SLOGAN', 'text::', 'The right tool for the right job!', 'Site slogan', 2),
(24, 'Site', 'AUTHOR', 'text::www@genome.arizona.edu', 'www@genome.arizona.edu', 'Site author''s email', 3),
(25, 'Profile', 'firstName', 'text::', '', 'First name', 0),
(26, 'Profile', 'lastName', 'text::', '', 'Last name', 1),
(27, 'Profile', 'email', 'text::', '', 'Email', 2),
(28, 'Display', 'usersPerPage', 'number:5,10,20,30,50,100:20', '30', 'Number of users per page<br>(for administrator only)', 100),
(29, 'Display', 'programsPerPage', 'number:5,10,15,20,25,30:20', '30', 'Number of programs per page<br>(for administrator only)', 100),
(30, 'Display', 'showTip', 'number:No,Yes:Yes', 'Yes', 'Show site tips', 11),
(31, 'Display', 'fileTypesPerPage', 'number:5,10,15,20,25,30:20', '30', 'Number of file types per page<br>(for administrator only)', 100),
(32, 'Display', 'linesForPreview', 'int::', '50', 'Lines for preview', 0),
(33, 'Site', 'barcode', 'int::100001', '348302', 'Last barcode<br>(Change with cautions)', 100),
(34, 'Site', 'smrtrun', 'int::1', '72', 'Last SMRT run<br>(Change with cautions)', 100),
(35, 'Display', 'groupsPerPage', 'number:5,10,20,30,50,100:20', '30', 'Number of groups per page<br>(for administrator only)', 100),
(36, 'Permission', 'asbProject', 'number:No,Yes:No', 'No', 'Assembly project', 0),
(37, 'Permission', 'assembly', 'number:No,Yes:No', 'No', 'Assembly', 0),
(38, 'Permission', 'box', 'number:No,Yes:No', 'No', 'Box', 0),
(39, 'Permission', 'freezer', 'number:No,Yes:No', 'No', 'Freezer', 0),
(40, 'Permission', 'genome', 'number:No,Yes:No', 'No', 'Genome', 0),
(41, 'Permission', 'item', 'number:No,Yes:No', 'No', 'Any item', 100),
(42, 'Permission', 'library', 'number:No,Yes:No', 'No', 'Library', 0),
(43, 'Permission', 'paclib', 'number:No,Yes:No', 'No', 'Paclib', 0),
(44, 'Permission', 'plate', 'number:No,Yes:No', 'No', 'Plate', 0),
(45, 'Permission', 'pool', 'number:No,Yes:No', 'No', 'BAC pool', 0),
(46, 'Permission', 'project', 'number:No,Yes:No', 'No', 'Project', 0),
(47, 'Permission', 'room', 'number:No,Yes:No', 'No', 'Room', 0),
(48, 'Permission', 'sample', 'number:No,Yes:No', 'No', 'Sample', 0),
(49, 'Permission', 'sequence', 'number:No,Yes:No', 'No', 'Sequence', 0),
(50, 'Permission', 'service', 'number:No,Yes:No', 'No', 'Service', 0),
(51, 'Permission', 'smrtrun', 'number:No,Yes:No', 'No', 'SMRT run', 0),
(52, 'Permission', 'smrtwell', 'number:No,Yes:No', 'No', 'SMRT well', 0),
(53, 'Permission', 'vector', 'number:No,Yes:No', 'No', 'Vector', 0),
(54, 'Permission', 'download', 'number:No,Yes:Yes', 'Yes', 'Download', 101),
(55, 'GPM', 'SEQTOSEQMINOVERLAP', 'int::1000', '1000', 'Seq to seq minimum overlap (bp)', 0),
(56, 'GPM', 'SEQTOSEQIDENTITY', 'int::99', '99', 'Seq to seq identity', 1),
(57, 'GPM', 'SEQTOGNMMINOVERLAP', 'int::1000', '1000', 'Seq to genome minimum overlap (bp)', 2),
(58, 'GPM', 'SEQTOGNMIDENTITY', 'int::98', '98', 'Seq to genome identity', 3),
(59, 'GPM', 'ENDTOENDMINOVERLAP', 'int::1000', '1000', 'End to end minimum overlap (bp)', 4),
(60, 'GPM', 'ENDTOENDIDENTITY', 'int::99', '99', 'End to end identity', 5),
(61, 'GPM', 'BESTOSEQMINOVERLAP', 'int::300', '300', 'BES to seq minimum overlap (bp)', 6),
(62, 'GPM', 'BESTOSEQIDENTITY', 'int::99', '99', 'BES to seq identity', 7),
(63, 'Site', 'RSDashboardURL', 'text::http://your.rsdashboard.url.or.ip', 'http://your.rsdashboard.url.or.ip', 'RS Dashboard URL', 10),
(64, 'Site', 'JOBURL', 'text::http://job.host.url.for.smrtportal:8080/smrtportal/api/jobs', 'http://job.host.url.for.smrtportal:8080/smrtportal/api/jobs', 'SMRT Portsl Job URL', 11),
(65, 'Site', 'JOBREALTIME', 'number:0,1:0', '0', 'Realtime Load Job List<br><sub>(0=No, 1=Yes)</sub>', 12);

-- --------------------------------------------------------

--
-- Table structure for table `user`
--

CREATE TABLE IF NOT EXISTS `user` (
  `id` int(5) unsigned NOT NULL AUTO_INCREMENT,
  `userName` varchar(25) CHARACTER SET utf8 COLLATE utf8_bin NOT NULL,
  `password` varchar(32) CHARACTER SET utf8 COLLATE utf8_bin NOT NULL,
  `role` varchar(25) COLLATE utf8_unicode_ci DEFAULT NULL,
  `creation` datetime NOT NULL,
  `activation` varchar(20) COLLATE utf8_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `userName` (`userName`)
) ENGINE=MyISAM  DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci;

--
-- Dumping data for table `user`
--

INSERT INTO `user` (`id`, `userName`, `password`, `role`, `creation`, `activation`) VALUES
(1, 'admin', '21232f297a57a5a743894a0e4a801fc3', 'admin', '1900-01-01 00:00:00', '1900-01-01 00:00:00');


-- --------------------------------------------------------

--
-- Table structure for table `userConfig`
--

CREATE TABLE IF NOT EXISTS `userConfig` (
  `id` int(5) unsigned NOT NULL AUTO_INCREMENT,
  `userId` int(5) NOT NULL,
  `configId` int(11) NOT NULL,
  `fieldValue` text CHARACTER SET utf8 COLLATE utf8_bin NOT NULL,
  PRIMARY KEY (`id`),
  KEY `userId` (`userId`),
  FULLTEXT KEY `fieldValue` (`fieldValue`)
) ENGINE=MyISAM  DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci;
--
-- Dumping data for table `userConfig`
--

INSERT INTO `userConfig` (`id`, `userId`, `configId`, `fieldValue`) VALUES
(1, 1, 4, '10'),
(2, 1, 5, '10'),
(3, 1, 6, '20'),
(4, 1, 7, '15'),
(5, 1, 8, '25'),
(6, 1, 9, '15'),
(7, 1, 10, '20'),
(8, 1, 11, '15'),
(9, 1, 12, '/users/SHARED'),
(10, 1, 13, '/users/SHARED'),
(11, 1, 14, '1,2,3'),
(12, 1, 15, ''),
(13, 1, 16, '5'),
(14, 1, 17, '01/01/1900'),
(15, 1, 18, '1657 E. Helen Street'),
(16, 1, 19, 'Tucson'),
(17, 1, 20, 'Arizona'),
(18, 1, 21, '85718'),
(19, 1, 22, 'USA');

-- --------------------------------------------------------

--
-- Table structure for table `userCookie`
--

CREATE TABLE IF NOT EXISTS `userCookie` (
  `cookie` char(32) COLLATE utf8_unicode_ci NOT NULL,
  `userId` int(10) unsigned NOT NULL,
  `datetime` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `ipAddress` char(15) COLLATE utf8_unicode_ci NOT NULL,
  PRIMARY KEY (`cookie`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
