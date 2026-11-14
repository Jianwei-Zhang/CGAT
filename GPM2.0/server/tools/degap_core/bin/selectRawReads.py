import re
import sys
import os
import operator
import numpy as np
import Bio
from Bio import SeqIO
import pysam
from pysam import AlignmentFile
import subprocess

class selectRawReads(object):
	def __init__(self,parameterlist,seedLen):
		self.seedLen=seedLen
		# Handle different parameter list lengths for different modes and versions
		if len(parameterlist)==9:
			# ctglinker mode (old format)
			self.mode,self.remove,self.thread,self.reads,self.out,self.genomeSeq,self.edge,self.filterDepthHifi,self.MaximunExtensionLength=parameterlist[:9]
			self.readsDict = None
			self.data_type = 'hifi'
			self.filterDepthOnt = None
			self.ont_reads = None
			self.inputSeq=self.genomeSeq
			self.inputSeqDict={}
			for gseq in SeqIO.parse(self.inputSeq,'fasta'):
				self.inputSeqDict[gseq.id]=len(gseq.seq)
		elif len(parameterlist)==10:
			# ctglinker mode (with data_type)
			self.mode,self.remove,self.thread,self.reads,self.out,self.genomeSeq,self.edge,self.filterDepthHifi,self.MaximunExtensionLength,self.data_type=parameterlist[:10]
			self.readsDict = None
			self.filterDepthOnt = None
			self.ont_reads = None
			self.inputSeq=self.genomeSeq
			self.inputSeqDict={}
			for gseq in SeqIO.parse(self.inputSeq,'fasta'):
				self.inputSeqDict[gseq.id]=len(gseq.seq)
		elif len(parameterlist)==12 and 'ctglinker' in parameterlist:
			# ctglinker mode (new format with filterDepthHifi, filterDepthOnt, data_type, ont_reads)
			self.mode,self.remove,self.thread,self.reads,self.out,self.genomeSeq,self.edge,self.filterDepthHifi,self.filterDepthOnt,self.MaximunExtensionLength,self.data_type,self.ont_reads=parameterlist
			self.readsDict = None
			self.inputSeq=self.genomeSeq
			self.inputSeqDict={}
			for gseq in SeqIO.parse(self.inputSeq,'fasta'):
				self.inputSeqDict[gseq.id]=len(gseq.seq)
		elif len(parameterlist)==12:
			# gapfiller mode (old format)
			self.mode,self.remove,self.thread,self.reads,self.out,self.seqLeft,self.seqRight,self.flag,self.edge,self.filterDepthHifi,self.MaximunExtensionLength=parameterlist[:11]
			self.readsDict = parameterlist[11] if len(parameterlist) > 11 else None
			self.data_type = 'hifi'
			self.filterDepthOnt = None
			self.ont_reads = None
		elif len(parameterlist)==13:
			# Handle case where readsDict was accidentally included in parameter list
			# This can happen if parameter list was modified before selectRawReads call
			if 'ctglinker' in parameterlist:
				# ctglinker mode with extra parameter - take first 12
				self.mode,self.remove,self.thread,self.reads,self.out,self.genomeSeq,self.edge,self.filterDepthHifi,self.filterDepthOnt,self.MaximunExtensionLength,self.data_type,self.ont_reads=parameterlist[:12]
				self.readsDict = None
				self.inputSeq=self.genomeSeq
				self.inputSeqDict={}
				for gseq in SeqIO.parse(self.inputSeq,'fasta'):
					self.inputSeqDict[gseq.id]=len(gseq.seq)
			else:
				# gapfiller mode with extra parameter - take first 12
				self.mode,self.remove,self.thread,self.reads,self.out,self.seqLeft,self.seqRight,self.flag,self.edge,self.filterDepthHifi,self.MaximunExtensionLength=parameterlist[:11]
				self.readsDict = parameterlist[11] if len(parameterlist) > 11 else None
				self.data_type = parameterlist[12] if len(parameterlist) > 12 else 'hifi'
				self.filterDepthOnt = None
				self.ont_reads = None
		elif len(parameterlist)==14:
			# gapfiller mode (new format with filterDepthHifi, filterDepthOnt, data_type, ont_reads)
			self.mode,self.remove,self.thread,self.reads,self.out,self.seqLeft,self.seqRight,self.flag,self.edge,self.filterDepthHifi,self.filterDepthOnt,self.MaximunExtensionLength,self.data_type,self.ont_reads=parameterlist
			self.readsDict = None
		else:
			raise ValueError(f"Unsupported parameter list length: {len(parameterlist)}. Expected 9, 10, 12, 13, or 14 parameters.")

		# Determine which data types to process based on filter settings
		self.process_hifi = self.filterDepthHifi is not None
		# In pure ONT mode, reads are provided via self.reads (not self.ont_reads),
		# so we should allow depth filtering whenever filterDepthOnt is set.
		if self.data_type == 'ont':
			self.process_ont = self.filterDepthOnt is not None
		else:
			# In mixed mode, ONT reads are provided separately via self.ont_reads
			self.process_ont = self.filterDepthOnt is not None and self.ont_reads is not None

		# Handle gapfiller mode setup
		if hasattr(self, 'seqLeft'):
			self.inputSeq=self.out+"/Genome.inputCtg.fa"
			filet=open(self.inputSeq,'w')
			self.inputSeqDict={}
			for gseq in SeqIO.parse(self.seqLeft,'fasta'):
				l='>'+gseq.id+"\n"+str(gseq.seq)+"\n"
				filet.writelines(l)
				self.inputSeqDict[gseq.id]=len(gseq.seq)
			for gseq in SeqIO.parse(self.seqRight,'fasta'):
				l='>'+gseq.id+"\n"+str(gseq.seq)+"\n"
				filet.writelines(l)
				self.inputSeqDict[gseq.id]=len(gseq.seq)
			filet.close()
		self.selectRawReadsLog=self.out+"/Genome.inputCtg.mappedReads.log"
		self.alnTag=1	
		if os.path.exists(self.selectRawReadsLog)==True and os.path.getsize(self.selectRawReadsLog)!=0:
			file1=open(self.selectRawReadsLog,'r')
			for row in file1:
				row1=row.rstrip().split('\t')
				if row1[0]=='alnFile':
					self.alnFile=row1[1]
				elif row1[0]=='alnCommand':
					self.alnCommand=row1[1]
				elif row1[0]=='alnTag':
					self.alnTag=int(row1[1])
			file1.close()
		else:
			self.alnFile,self.alnCommand,self.alnTag=self.minimap2()
		if self.alnTag!=0:
			self.alnFile,self.alnCommand,self.alnTag=self.minimap2()
		l='alnFile\t'+self.alnFile+"\nalnCommand\t"+self.alnCommand+"\nalnTag\t"+str(self.alnTag)+"\n"
		file1=open(self.selectRawReadsLog,'w')
		file1.writelines(l)
		file1.close()
		self.alnSortDepth=self.getDepth()

		self.readName,self.readFile,self.readLog=self.getReads()

	def getReads(self):
		readName=self.out+"/Genome.inputCtg.usefullReads.txt"

		# Depth filtering always outputs FASTA format
		readFile=self.out+"/Genome.inputCtg.usefullReads.fasta"
		readLog=self.out+"/Genome.inputCtg.usefullReads.log"

		# Initialize ONT-specific files for mixed mode
		if self.data_type == 'mixed' and self.process_ont:
			self.ont_readName = self.out+"/Genome.inputCtg.usefullReads.ont.txt"
			self.ont_readFile = self.out+"/Genome.inputCtg.usefullReads.ont.fasta"

		if os.path.exists(readLog)==True and os.path.getsize(readLog)!=0:
			return readName,readFile,readLog
		else:
			# Process HiFi reads if filterDepthHifi is set
			if self.process_hifi:
				print(f"Processing HiFi reads with filterDepthHifi={self.filterDepthHifi}")
				self._processReadsWithDepthFilter(readName, readFile, self.filterDepthHifi, 'hifi')

			# Process ONT reads if filterDepthOnt is set and we have ONT reads
			if self.process_ont:
				print(f"Processing ONT reads with filterDepthOnt={self.filterDepthOnt}")
				# For mixed mode, process ONT reads separately
				if self.data_type == 'mixed':
					self._processONTReads()
				else:
					# Pure ONT mode
					self._processReadsWithDepthFilter(readName, readFile, self.filterDepthOnt, 'ont')

			# If neither filter is set, this shouldn't happen as we check before calling selectRawReads
			if not self.process_hifi and not self.process_ont:
				raise ValueError("No filter depth parameters set, selectRawReads should not be called")

			return readName,readFile,readLog

	def _processReadsWithDepthFilter(self, readName, readFile, filterDepth, read_type, custom_aln_file=None, custom_depth_file=None):
		"""Process reads with depth filtering for specified read type"""
		# Use custom files for ONT processing, or default files for HiFi
		depth_file = custom_depth_file if custom_depth_file else self.alnSortDepth
		aln_file = custom_aln_file if custom_aln_file else self.alnFile

		# Ensure readsDict is available (build on the fly if not provided)
		temp_idx_path = None
		if getattr(self, 'readsDict', None) is None:
			try:
				# Use a temporary index filename to avoid interfering with main pipeline indices
				if self.data_type == 'ont':
					idx_path = os.path.join(self.out, "ont_reads.depthfilter.idx")
				else:
					# default and mixed mode both use HiFi reads here
					idx_path = os.path.join(self.out, "hifi_reads.depthfilter.idx")
				temp_idx_path = idx_path
				# Determine input format
				if (("processed_reads" in self.reads) and self.reads.endswith((".fa", ".fasta"))):
					reads_format = 'fasta'
				elif self.reads.endswith((".fastq", ".fq", ".fastq.gz", ".fq.gz")):
					reads_format = 'fastq'
				else:
					reads_format = 'fasta'
				# Always (re)build temporary index to ensure it points to current self.reads
				self.readsDict = SeqIO.index_db(idx_path, self.reads, reads_format)
				print(f"Built temporary reads index for depth filtering: {idx_path} (format={reads_format})")
			except Exception as e:
				print(f"ERROR: failed to build reads index for depth filtering: {e}")
				raise

		file1=open(depth_file,'r')
		depth=[]
		for row in file1:
			row1=row.rstrip().split('\t')
			depth.append(int(row1[-1]))
		file1.close()
		a=np.argmax(np.bincount(depth))

		a1=a*(2.0-filterDepth)
		a2=a*filterDepth
		readsname=[]
		file1=open(self.alnSortDepth,'r')
		loci={}
		for row in file1:
			row1=row.rstrip().split('\t')
			d=int(row1[-1])
			if d<=a2 or d>=a1:
				if row1[0] in loci:
					lo=loci[row1[0]]
				else:
					lo=[]
				lo.append(int(row1[1]))
				loci[row1[0]]=lo

		file1.close()

		file1=open(readName,'w')
		file2=open(readFile,'w')
		commendlines='samtools index -bc -@ '+self.thread+" "+aln_file
		os.system(commendlines)
		bamFile=AlignmentFile(aln_file,"rb")

		loci1={}
		for k,v in loci.items():
			v1=self.mergelist(v)
			loci[k]=v1
			print (k)
			print (len(v))
			print (len(v1))

			for i in v1:
				s,e=i
				for r in bamFile.fetch(k, s, e):
					l=r.query_name+"\n"
					file1.writelines(l)
		for k,v in self.inputSeqDict.items():
			print (k,v)
			# Fix: ensure end position doesn't exceed sequence length
			for r in bamFile.fetch(k, 0, min(self.seedLen, v)):
				l=r.query_name+"\n"
				file1.writelines(l)
			# Fix: ensure start position is not negative
			start_pos = max(0, v - self.seedLen)
			for r in bamFile.fetch(k, start_pos, v):
				l=r.query_name+"\n"
				file1.writelines(l)


		readlist=[]
		Chrlist=[]
		for r in bamFile:
			if r.reference_name not in Chrlist:
				Chrlist.append(r.reference_name)
				print (r.reference_name)
			# Guard against missing index entries
			if self.readsDict is None or r.query_name not in self.readsDict:
				continue
			gseq=self.readsDict[r.query_name]
			queryLen=len(gseq.seq)
			if r.is_unmapped==True:
				l=r.query_name+"\n"
				file1.writelines(l)
			else:
				if queryLen==0 or float(r.query_alignment_length)/queryLen<0.99:
					l=r.query_name+"\n"
					file1.writelines(l)
		file1.close()
		commondline='cat '+readName+" | sort | uniq >"+self.out+'/temp'
		os.system(commondline)
		commondline='mv '+self.out+'/temp '+readName
		os.system(commondline)
		file1=open(readName)
		for row in file1:
			row1=row.rstrip()
			if self.readsDict is None or row1 not in self.readsDict:
				continue
			gseq=self.readsDict[row1]
			# Depth filtering always outputs FASTA format
			l = f">{gseq.description}\n{gseq.seq}\n"
			file2.writelines(l)

		file2.close()
		bamFile.close()

		# Clean up temporary index to avoid interfering with main index build
		try:
			if 'temp_idx_path' in locals() and temp_idx_path and os.path.exists(temp_idx_path):
				os.remove(temp_idx_path)
		except Exception:
			pass

		# Write log
		readLog = self.out+"/Genome.inputCtg.usefullReads.log"
		file1=open(readLog,'w')
		l='depthThreshold(>)\t'+str(a)+'\nreadName\t'+readName+"\nreadFile\t"+readFile+"\nreadType\t"+read_type+"\nfilterDepth\t"+str(filterDepth)+"\n"
		file1.writelines(l)
		file1.close()

	def _processONTReads(self):
		"""Process ONT reads separately in mixed mode"""
		print("Processing ONT reads in mixed mode...")

		# Create ONT reads index (temporary for depth filtering)
		ont_idx_path = self.out + "/ont_reads.depthfilter.idx"
		print("Creating temporary ONT reads index for depth filtering...")
		print(f"ONT reads file: {self.ont_reads}")
		# For mixed mode, ONT reads should now be in FASTA format (converted from FASTQ)
		# Check if it's a converted FASTA file from processed_reads directory
		if 'processed_reads' in self.ont_reads and self.ont_reads.endswith(('.fa', '.fasta')):
			ont_format = 'fasta'
			print("Using FASTA format for converted ONT reads")
		elif self.ont_reads.endswith(('.fastq', '.fq', '.fastq.gz', '.fq.gz')):
			ont_format = 'fastq'
			print("Using FASTQ format for original ONT reads")
		else:
			ont_format = 'fasta'
			print("Defaulting to FASTA format for ONT reads")

		# Always (re)build temporary ONT index to ensure it points to current self.ont_reads
		ont_readsDict = SeqIO.index_db(ont_idx_path, self.ont_reads, ont_format)

		# Store ONT readsDict for later use
		self.ont_readsDict = ont_readsDict

		# Create ONT-specific alignment and depth analysis
		ont_aln_file = self.out + "/Genome.inputCtg.mappedReads.ont.bam"
		ont_depth_file = self.out + "/Genome.inputCtg.mappedReads.ont.depth.txt"

		# 1. Align ONT reads to input sequence
		print("Aligning ONT reads to input sequence...")
		ont_aln_cmd = f"minimap2 -t {self.thread} -Y -ax map-ont {self.inputSeq} {self.ont_reads} | samtools sort -@ {self.thread} -o {ont_aln_file}"

		if not os.path.exists(ont_aln_file) or os.path.getsize(ont_aln_file) == 0:
			try:
				subprocess.run(ont_aln_cmd, shell=True, check=True)
				print("ONT alignment completed")

				# Create BAM index
				index_cmd = f"samtools index {ont_aln_file}"
				subprocess.run(index_cmd, shell=True, check=True)
				print("ONT BAM index created")
			except subprocess.CalledProcessError as e:
				print(f"ONT alignment or indexing failed: {e}")
				return

		# 2. Calculate depth for ONT reads
		print("Calculating ONT reads depth...")
		if not os.path.exists(ont_depth_file) or os.path.getsize(ont_depth_file) == 0:
			depth_cmd = f"samtools depth -aa {ont_aln_file} > {ont_depth_file}"
			try:
				subprocess.run(depth_cmd, shell=True, check=True)
				print("ONT depth calculation completed")
			except subprocess.CalledProcessError as e:
				print(f"ONT depth calculation failed: {e}")
				return

		# 3. Apply depth filtering to ONT reads
		self._processReadsWithDepthFilterONT(
			self.ont_readName,
			self.ont_readFile,
			self.filterDepthOnt,
			'ont',
			ont_aln_file,
			ont_depth_file,
			ont_readsDict
		)
		# Clean up temporary ONT index file
		try:
			if os.path.exists(ont_idx_path):
				os.remove(ont_idx_path)
		except Exception:
			pass

	def _processReadsWithDepthFilterONT(self, readName, readFile, filterDepth, read_type, aln_file, depth_file, reads_dict):
		"""Process ONT reads with depth filtering using custom files and reads dictionary"""
		import numpy as np

		# Read depth information
		file1=open(depth_file,'r')
		depth=[]
		for row in file1:
			row1=row.rstrip().split('\t')
			depth.append(int(row1[-1]))
		file1.close()
		a=np.argmax(np.bincount(depth))

		a1=a*(2.0-filterDepth)
		a2=a*filterDepth
		readsname=[]
		file1=open(depth_file,'r')
		loci={}
		for row in file1:
			row1=row.rstrip().split('\t')
			d=int(row1[-1])
			if d<=a2 or d>=a1:
				if row1[0] in loci:
					lo=loci[row1[0]]
				else:
					lo=[]
				lo.append(int(row1[1]))
				loci[row1[0]]=lo

		file1.close()

		file1=open(readName,'w')
		file2=open(readFile,'w')
		commendlines='samtools index -bc -@ '+self.thread+" "+aln_file
		os.system(commendlines)
		bamFile=AlignmentFile(aln_file,"rb")

		loci1={}
		for k,v in loci.items():
			v1=self.mergelist(v)
			loci[k]=v1
			print (k)
			print (len(v))
			print (len(v1))

			for i in v1:
				s,e=i
				for r in bamFile.fetch(k, s, e):
					l=r.query_name+"\n"
					file1.writelines(l)
		for k,v in self.inputSeqDict.items():
			print (k,v)
			# Fix: ensure end position doesn't exceed sequence length
			for r in bamFile.fetch(k, 0, min(self.seedLen, v)):
				l=r.query_name+"\n"
				file1.writelines(l)
			# Fix: ensure start position is not negative
			start_pos = max(0, v - self.seedLen)
			for r in bamFile.fetch(k, start_pos, v):
				l=r.query_name+"\n"
				file1.writelines(l)


		readlist=[]
		Chrlist=[]
		for r in bamFile:
			if r.reference_name not in Chrlist:
				Chrlist.append(r.reference_name)
				print (r.reference_name)
			gseq=reads_dict[r.query_name]  # Use custom reads_dict
			queryLen=len(gseq.seq)
			if r.is_unmapped==True:
				l=r.query_name+"\n"
				file1.writelines(l)
			else:
				if float(r.query_alignment_length)/queryLen<0.99:
					l=r.query_name+"\n"
					file1.writelines(l)
		file1.close()
		commondline='cat '+readName+" | sort | uniq >"+self.out+'/temp.ont'
		os.system(commondline)
		commondline='mv '+self.out+'/temp.ont '+readName
		os.system(commondline)
		file1=open(readName)
		for row in file1:
			row1=row.rstrip()
			gseq=reads_dict[row1]  # Use custom reads_dict

			# Depth filtering always outputs FASTA format
			l = f">{gseq.description}\n{gseq.seq}\n"
			file2.writelines(l)

		file2.close()
		bamFile.close()

		# Write log
		readLog = self.out+"/Genome.inputCtg.usefullReads.ont.log"
		file1=open(readLog,'w')
		l='depthThreshold(>)\t'+str(a)+'\nreadName\t'+readName+"\nreadFile\t"+readFile+"\nreadType\t"+read_type+"\nfilterDepth\t"+str(filterDepth)+"\n"
		file1.writelines(l)
		file1.close()

		print(f"ONT reads filtering completed: {readFile}")

	def mergelist(self,v):
		v1=[]
		it=[v[0],v[0]]
		for i in v[1:]:
			if i==it[1]+1:
				it[1]=i
			else:
				v1.append(it)
				it=[i,i]
		return v1

	def getDepth(self):
		alnSortName=self.out+"/Genome.inputCtg.mappedReads.sort.bam"
		commandline="samtools sort -@ "+self.thread+" -o "+alnSortName+" "+self.alnFile
		if os.path.exists(alnSortName)!=True or os.path.getsize(alnSortName)==0:
			output=os.system(commandline)
		alnSortDepth=self.out+"/Genome.inputCtg.mappedReads.sort.depth.txt"
		if os.path.exists(alnSortDepth)!=True or os.path.getsize(alnSortDepth)==0:
			commandline="samtools depth -aa  "+alnSortName+" >"+alnSortDepth
			output=os.system(commandline)
		#return alnSortName,alnSortDepth
		return alnSortDepth
			

	def minimap2(self):
		alnname=self.out+"/Genome.inputCtg.mappedReads.sort.bam"

		# Choose appropriate minimap2 preset based on data type
		if self.data_type == 'ont':
			preset = "map-ont"
		elif self.data_type == 'hifi':
			preset = "asm20"
		elif self.data_type == 'mixed':
			preset = "asm20"  # Use HiFi preset for primary reads
		else:
			preset = "asm20"  # Default

		commandline="minimap2 -t "+self.thread+" -Y -ax "+preset+" "+self.inputSeq+" "+self.reads+" | samtools sort -@ "+self.thread+" -o "+alnname

		if os.path.exists(alnname)==True and os.path.getsize(alnname)!=0 and self.alnTag==0:
			return alnname,commandline,str(0)
		else:
			output=os.system(commandline)
			minimaptag=1
			if output!=0:
				while output!=0:
					output=os.system(commandline)
					minimaptag+=1
					if minimaptag>=3:
						print ("minimap2 cannot do proper alignment!!!")
						sys.exit()
			return alnname,commandline,str(output)
