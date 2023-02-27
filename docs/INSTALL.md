# [Pangu LIMS Docs](README.md)
## Installation Instruction

1) Download LIMS source files and unzip the file on your own local system.

2) Make a new directory under both /var/www/cgi-bin/ directory and /var/www/html/ directory. For example, the new directory named "lims". The commands are:
```
$ mkdir /var/www/cgi-bin/lims
$ mkdir /var/www/html/lims
```
3) Copy all the files and directories in the "cgi-bin" directory (e.g. ~/LIMS-master/cgi-bin/) to the /var/www/cgi-bin/lims directory:
```
$ cp -r ~/LIMS-master/cgi-bin/* /var/www/cgi-bin/lims/
```
4) Copy all the files and directories in the "htdocs" directory (e.g. ~/LIMS-master/htdocs/) to /var/www/html/lims directory:
```
$ cp -r ~/LIMS-master/htdocs/* /var/www/html/lims/
```
5) Make all files in /var/www/cgi-bin/lims/ executable: 
```
$ chmod 775 /usr/www/cgi-bin/lims/*
```
6) Activate the index file, rename the "index.html.tmpl" file in /var/www/html/lims/ directory as "index.html":
```
$ mv /var/www/html/lims/index.html.tmpl /var/www/html/lims/index.html
```
7) Activate the configuration file, rename the "main.conf.tmpl" file in the /var/www/cgi-bin/lims/ directory as "main.conf":
```
$ mv /var/www/cgi-bin/lims/main.conf.tmpl /var/www/cgi-bin/lims/main.conf
```
8) Install the following perl modules for GPM as needed: 
```
$ cpan SVG
$ cpan CGI
$ cpan URI-Escape-XS
$ cpan Math::Trig
$ cpan JSON
$ cpan JSON::XS
```
The source of these modules are:

- Scalable Vector Graphics (SVG) Library http://search.cpan.org/dist/SVG/
- CGI http://search.cpan.org/dist/CGI/
- URI-Escape-XS http://search.cpan.org/dist/URI-Escape-XS/
- Math::Trig http://search.cpan.org/~zefram/Math-Complex-1.59/lib/Math/Trig.pm
- JSON http://search.cpan.org/~makamaka/JSON-2.53/lib/JSON.pm
- JSON::XS https://metacpan.org/pod/JSON::XS

9) Download the blast+(ftp://ftp.ncbi.nih.gov/blast/) then install it in /usr/biosoft/ directory and create symbol link in the /var/www/cgi-bin/lims/ document by using the command: 
```
$ ln -s /usr/biosoft/blast+/
```
10) Make a new MySQL database named "lims" for LIMS. The command are:
```
$ mysql -u root -p
Enter password: ********
mysql> CREATE DATABASE IF NOT EXISTS lims;
mysql> use lims;
mysql> source ~/LIMS-master/sql/lims.sql
```
11) Open the "main.conf" file in /var/www/cgi-bin/lims/ directory and complete the information as follow:

```
USERNAME = root #Your username for accessing MySQL
PASSWORD = ******** #Your password for accessing MySQL
DATABASE = lims #(The DATABASE-NAME YOU CREATED ON STEP 10)
DBHOST = localhost
HOSTURL = http://YOUR-HOSTURL
CGIBINDIR = /var/www/cgi-bin/lims
CGIBIN = /cgi-bin/lims
HTMLDIR = /var/www/html/lims
HTDOCS =  /lims
DATADIR = /var/www/html/lims/data
TMPDIR = /var/www/html/lims/data/tmp # a tmp directory, make sure it's writable
TMPURL = /lims/data/tmp
JOBDIR = /var/www/html/lims/data/jobs #optional --leave this blank if you don't know what this is
VECTOR = /var/www/html/lims/data/pAGIBAC1_HindIII.txt #optional --leave this blank if you don't know what this is
VECTORLENGTH = 7522 #optional --leave this blank if you don't know what this is
POLISHED = /var/www/html/lims/data/polished #optional --leave this blank if you don't know what this is
POLISHEDURL = /lims/data/polished #optional --leave this blank if you don't know what this is
```
Make sure that you enter the correct path of your files and don't forget to bring the directory name you created on step 2. In this text we add "lims" into the path.

12) To optimize LIMS, change some settings in the /etc/my.cnf file as below, then restart MySQL service:
```
#set max_allowed_packet to 512M for loading long sequences, like maize genome
#The maximum size of one packet or any generated/intermediate string
max_allowed_packet      = 512M

#set myisam_sort_buffer_size to 2G, system default is 8M
myisam_sort_buffer_size = 2G

#The minimum length of the word to be included in a MyISAM FULLTEXT index, system default is 4
ft_min_word_len = 1
```
13) Visit your local instance at http://YOUR-HOSTURL/lims on your Server. The username and password are "admin/admin". Before loading data, please make sure the above link is alive. Any questions during installation, please contact Jianwei Zhang (jzhang@mail.hzau.edu.cn).