#!/usr/bin/env python3
# -*-coding:utf-8 -*-

#**********************************************************************************
#filename:GAP_Filler.py
#*********************************************************************************

import re
import os
import sys
import getopt
import pysam
from pysam import AlignmentFile
import Bio
from Bio import SeqIO
import GapFillerClass
from GapFillerClass import GapFillerClass,mummer

class GapFiller(object):
	def __init__(self,parameterlist, kparameters):
		# Handle different parameter list lengths due to dynamic construction in DEGAP.py
		# Current structure after DEGAP.py processing:
		# [mode, remove, thread, reads, out, seqleft, seqright, flag, edge, filterDepthHifi, filterDepthOnt, MaximumExtensionLength, MaximumExtensionRound, data_type, ont_reads, readsDict, maxReadsLen, seedLen]

		print(f"GapFiller received parameter list with {len(parameterlist)} parameters")
		print(f"Parameter list: {parameterlist}")

		if len(parameterlist) == 21:  # New format with MaximumExtensionRound and ONT readsDict: [0-14: original params, 15: readsDict, 16: maxReadsLen, 17: hifiSeedLen, 18: ontSeedLen, 19: original_reads_info, 20: ont_readsDict]
			self.mode = parameterlist[0]
			self.remove = parameterlist[1]
			self.thread = parameterlist[2]
			self.reads = parameterlist[3]
			self.out = parameterlist[4]
			self.seqleft = parameterlist[5]
			self.seqright = parameterlist[6]
			self.flag = parameterlist[7]
			self.edge = parameterlist[8]
			self.filterDepthHifi = parameterlist[9]
			self.filterDepthOnt = parameterlist[10]
			self.MaximunExtensionLength = parameterlist[11]
			self.MaximumExtensionRound = parameterlist[12]
			self.data_type = parameterlist[13]
			self.ont_reads = parameterlist[14]
			self.readsDict = parameterlist[15]
			self.maxReadsLen = parameterlist[16]
			self.hifiSeedLen = parameterlist[17]
			self.ontSeedLen = parameterlist[18]
			self.original_reads_info = parameterlist[19]
			self.ont_readsDict = parameterlist[20]

			# Set seedLen for backward compatibility (use HiFi seed length as primary)
			self.seedLen = self.hifiSeedLen
			# For backward compatibility, set filterDepth to filterDepthHifi if it exists
			self.filterDepth = self.filterDepthHifi if self.filterDepthHifi is not None else self.filterDepthOnt

		elif len(parameterlist) == 20:  # Previous format with ONT readsDict but no MaximumExtensionRound: [0-13: original params, 14: readsDict, 15: maxReadsLen, 16: hifiSeedLen, 17: ontSeedLen, 18: original_reads_info, 19: ont_readsDict]
			self.mode = parameterlist[0]
			self.remove = parameterlist[1]
			self.thread = parameterlist[2]
			self.reads = parameterlist[3]
			self.out = parameterlist[4]
			self.seqleft = parameterlist[5]
			self.seqright = parameterlist[6]
			self.flag = parameterlist[7]
			self.edge = parameterlist[8]
			self.filterDepthHifi = parameterlist[9]
			self.filterDepthOnt = parameterlist[10]
			self.MaximunExtensionLength = parameterlist[11]
			self.MaximumExtensionRound = None  # Default value for backward compatibility
			self.data_type = parameterlist[12]
			self.ont_reads = parameterlist[13]
			self.readsDict = parameterlist[14]
			self.maxReadsLen = parameterlist[15]
			self.hifiSeedLen = parameterlist[16]
			self.ontSeedLen = parameterlist[17]
			self.original_reads_info = parameterlist[18]
			self.ont_readsDict = parameterlist[19]

			# Set seedLen for backward compatibility (use HiFi seed length as primary)
			self.seedLen = self.hifiSeedLen
			# For backward compatibility, set filterDepth to filterDepthHifi if it exists
			self.filterDepth = self.filterDepthHifi if self.filterDepthHifi is not None else self.filterDepthOnt

		elif len(parameterlist) == 19:  # Previous format with dual seed lengths: [0-13: original params, 14: readsDict, 15: maxReadsLen, 16: hifiSeedLen, 17: ontSeedLen, 18: original_reads_info]
			self.mode = parameterlist[0]
			self.remove = parameterlist[1]
			self.thread = parameterlist[2]
			self.reads = parameterlist[3]
			self.out = parameterlist[4]
			self.seqleft = parameterlist[5]
			self.seqright = parameterlist[6]
			self.flag = parameterlist[7]
			self.edge = parameterlist[8]
			self.filterDepthHifi = parameterlist[9]
			self.filterDepthOnt = parameterlist[10]
			self.MaximunExtensionLength = parameterlist[11]
			self.MaximumExtensionRound = None  # Default value for backward compatibility
			self.data_type = parameterlist[12]
			self.ont_reads = parameterlist[13]
			self.readsDict = parameterlist[14]
			self.maxReadsLen = parameterlist[15]
			self.hifiSeedLen = parameterlist[16]
			self.ontSeedLen = parameterlist[17]
			self.original_reads_info = parameterlist[18]

			# For backward compatibility, set dual seed lengths to same value
			# For backward compatibility, set filterDepth to filterDepthHifi if it exists
			self.filterDepth = self.filterDepthHifi if self.filterDepthHifi is not None else self.filterDepthOnt
			# Set ont_readsDict to None for backward compatibility
			self.ont_readsDict = None

		elif len(parameterlist) == 18:  # Previous format with original_reads_info: [0-13: original params, 14: readsDict, 15: maxReadsLen, 16: seedLen, 17: original_reads_info]
			self.mode = parameterlist[0]
			self.remove = parameterlist[1]
			self.thread = parameterlist[2]
			self.reads = parameterlist[3]
			self.out = parameterlist[4]
			self.seqleft = parameterlist[5]
			self.seqright = parameterlist[6]
			self.flag = parameterlist[7]
			self.edge = parameterlist[8]
			self.filterDepthHifi = parameterlist[9]
			self.filterDepthOnt = parameterlist[10]
			self.MaximunExtensionLength = parameterlist[11]
			self.MaximumExtensionRound = None  # Default value for backward compatibility
			self.data_type = parameterlist[12]
			self.ont_reads = parameterlist[13]
			self.readsDict = parameterlist[14]
			self.maxReadsLen = parameterlist[15]
			self.seedLen = parameterlist[16]
			self.original_reads_info = parameterlist[17]

			# For backward compatibility, set dual seed lengths to same value
			self.hifiSeedLen = self.seedLen
			self.ontSeedLen = self.seedLen
			# For backward compatibility, set filterDepth to filterDepthHifi if it exists
			self.filterDepth = self.filterDepthHifi if self.filterDepthHifi is not None else self.filterDepthOnt
			# Set ont_readsDict to None for backward compatibility
			self.ont_readsDict = None

		elif len(parameterlist) == 17:  # Previous format: [0-13: original params, 14: readsDict, 15: maxReadsLen, 16: seedLen]
			self.mode = parameterlist[0]
			self.remove = parameterlist[1]
			self.thread = parameterlist[2]
			self.reads = parameterlist[3]
			self.out = parameterlist[4]
			self.seqleft = parameterlist[5]
			self.seqright = parameterlist[6]
			self.flag = parameterlist[7]
			self.edge = parameterlist[8]
			self.filterDepthHifi = parameterlist[9]
			self.filterDepthOnt = parameterlist[10]
			self.MaximunExtensionLength = parameterlist[11]
			self.MaximumExtensionRound = None  # Default value for backward compatibility
			self.data_type = parameterlist[12]
			self.ont_reads = parameterlist[13]
			self.readsDict = parameterlist[14]
			self.maxReadsLen = parameterlist[15]
			self.seedLen = parameterlist[16]
			self.original_reads_info = None  # Not available in old format

			# For backward compatibility, set dual seed lengths to same value
			self.hifiSeedLen = self.seedLen
			self.ontSeedLen = self.seedLen
			# For backward compatibility, set filterDepth to filterDepthHifi if it exists
			self.filterDepth = self.filterDepthHifi if self.filterDepthHifi is not None else self.filterDepthOnt
			# Set ont_readsDict to None for backward compatibility
			self.ont_readsDict = None

		elif len(parameterlist) == 16:  # Legacy format with single filterDepth
			self.mode,self.remove,self.thread,self.reads,self.out,self.seqleft,self.seqright,self.flag,self.edge,self.filterDepth,self.MaximunExtensionLength,self.readsDict,self.maxReadsLen,self.seedLen,self.data_type,self.ont_reads=parameterlist
			self.MaximumExtensionRound = None  # Default value for backward compatibility
			self.filterDepthHifi = self.filterDepth
			self.filterDepthOnt = None

		elif len(parameterlist) == 15:  # Format with data_type but no ont_reads
			self.mode,self.remove,self.thread,self.reads,self.out,self.seqleft,self.seqright,self.flag,self.edge,self.filterDepth,self.MaximunExtensionLength,self.readsDict,self.maxReadsLen,self.seedLen,self.data_type=parameterlist
			self.MaximumExtensionRound = None  # Default value for backward compatibility
			self.ont_reads = None
			self.filterDepthHifi = self.filterDepth
			self.filterDepthOnt = None

		elif len(parameterlist) == 14:  # Old format without data_type
			self.mode,self.remove,self.thread,self.reads,self.out,self.seqleft,self.seqright,self.flag,self.edge,self.filterDepth,self.MaximunExtensionLength,self.readsDict,self.maxReadsLen,self.seedLen=parameterlist
			self.MaximumExtensionRound = None  # Default value for backward compatibility
			self.data_type = 'hifi'  # Default to HiFi for backward compatibility
			self.ont_reads = None
			self.filterDepthHifi = self.filterDepth
			self.filterDepthOnt = None

		else:
			print(f"Warning: Unexpected parameter list length: {len(parameterlist)}")
			print(f"Parameter list: {parameterlist}")

			# Try to handle as the most recent format (21 parameters)
			if len(parameterlist) >= 21:
				# Use the 21-parameter format
				self.mode = parameterlist[0]
				self.remove = parameterlist[1]
				self.thread = parameterlist[2]
				self.reads = parameterlist[3]
				self.out = parameterlist[4]
				self.seqleft = parameterlist[5]
				self.seqright = parameterlist[6]
				self.flag = parameterlist[7]
				self.edge = parameterlist[8]
				self.filterDepthHifi = parameterlist[9]
				self.filterDepthOnt = parameterlist[10]
				self.MaximunExtensionLength = parameterlist[11]
				self.MaximumExtensionRound = parameterlist[12] if len(parameterlist) > 12 else None
				self.data_type = parameterlist[13]
				self.ont_reads = parameterlist[14]
				self.readsDict = parameterlist[15]
				self.maxReadsLen = parameterlist[16]
				self.hifiSeedLen = parameterlist[17]
				self.ontSeedLen = parameterlist[18]
				self.original_reads_info = parameterlist[19]
				self.ont_readsDict = parameterlist[20] if len(parameterlist) > 20 else None

				self.seedLen = self.hifiSeedLen
				self.filterDepth = self.filterDepthHifi if self.filterDepthHifi is not None else self.filterDepthOnt
			else:
				# Fallback to basic parameter assignment
				raise ValueError(f"Unsupported parameter list length: {len(parameterlist)}")

		print(f"GapFiller initialized with:")
		print(f"  seedLen: {getattr(self, 'seedLen', 'NOT_SET')}")
		print(f"  hifiSeedLen: {getattr(self, 'hifiSeedLen', 'NOT_SET')}")
		print(f"  ontSeedLen: {getattr(self, 'ontSeedLen', 'NOT_SET')}")
		print(f"  maxReadsLen: {getattr(self, 'maxReadsLen', 'NOT_SET')}")
		print(f"  data_type: {getattr(self, 'data_type', 'NOT_SET')}")
		print(f"  filterDepthHifi: {getattr(self, 'filterDepthHifi', 'NOT_SET')}")
		print(f"  filterDepthOnt: {getattr(self, 'filterDepthOnt', 'NOT_SET')}")
		print(f"  ont_readsDict: {'Available' if getattr(self, 'ont_readsDict', None) is not None else 'None'}")
		print()

		# --- Type Conversion Sanity Check ---
		# Ensure all seed length parameters are integers, as they can be passed as strings.
		if hasattr(self, 'seedLen') and self.seedLen is not None:
			try:
				self.seedLen = int(self.seedLen)
			except (ValueError, TypeError):
				raise TypeError(f"seedLen must be an integer, but got: {self.seedLen}")
		
		if hasattr(self, 'hifiSeedLen') and self.hifiSeedLen is not None:
			try:
				self.hifiSeedLen = int(self.hifiSeedLen)
			except (ValueError, TypeError):
				raise TypeError(f"hifiSeedLen must be an integer, but got: {self.hifiSeedLen}")

		if hasattr(self, 'ontSeedLen') and self.ontSeedLen is not None:
			try:
				self.ontSeedLen = int(self.ontSeedLen)
			except (ValueError, TypeError):
				raise TypeError(f"ontSeedLen must be an integer, but got: {self.ontSeedLen}")

		# Parse kparameters - contains kmer_size, kmer_num, and kmer_filter
		if len(kparameters) == 3:
			# Standard format: [kmer_size, kmer_num, kmer_filter]
			self.kmer_size, self.kmer_num, self.kmer_filter = kparameters
		elif len(kparameters) == 2:
			# Legacy format: [kmer_size, kmer_num] (kmer_filter defaults to False)
			self.kmer_size, self.kmer_num = kparameters
			self.kmer_filter = False
		else:
			raise ValueError(f"Unsupported kparameters length: {len(kparameters)}. Expected 2 or 3 parameters.")

		self.resume_round = None  # Default: do not resume from checkpoint
		
		out=self.out
		self.log=out+"/process.log"
		if not os.path.exists(self.log):
			open(self.log,'w').close()
		self.summary=out+"/process.summary"
		if not os.path.exists(self.summary):
			open(self.summary,'w').close()
		self.agp=out+"/process.agp"
		self.usedReads=[]
		if not os.path.exists(self.agp):
			open(self.agp,'w').close()
		self.name=out.split('/')[-1]
		self.outfile=out+"/process"
		if not os.path.exists(self.outfile):
			os.makedirs(self.outfile)

		# Check if checkpoint file exists
		self.checkpoint_file = out+"/checkpoint.info"
		if os.path.exists(self.checkpoint_file):
			self.load_checkpoint()

		if self.flag=='left':
			self.initialSeq=self.seqleft
			self.terminalSeq=self.seqright
			self.tag='left'
		else:
			self.initialSeq=self.seqright
			self.terminalSeq=self.seqleft
			self.tag='right'

		# Add seed sequence length check logic
		self.check_and_adjust_seed_sequences()

		# Ensure original_reads_info is available for downstream use
		if not hasattr(self, 'original_reads_info'):
			self.original_reads_info = None

		self.Elongation=Elongation(self)
	
	def load_checkpoint(self):
		"""Read checkpoint information and decide which round to continue from"""
		try:
			with open(self.checkpoint_file, 'r') as f:
				checkpoint_data = f.read().strip()
				if checkpoint_data and checkpoint_data.startswith("round:"):
					self.resume_round = int(checkpoint_data.split("round:")[1])
					print(f"Found checkpoint information, will continue from round{self.resume_round}")
		except Exception as e:
			print(f"Failed to read checkpoint information: {e}")
			self.resume_round = None

	def save_checkpoint(self, round_num):
		"""Save current execution round"""
		try:
			with open(self.checkpoint_file, 'w') as f:
				f.write(f"round:{round_num}")
		except Exception as e:
			print(f"Failed to save checkpoint information: {e}")
	
	def check_and_adjust_seed_sequences(self):
		"""Check seed sequence length, use entire sequence if shorter than seedLen"""
		try:
			# Check initial seed sequences
			for seq_file in [self.initialSeq, self.terminalSeq]:
				if not os.path.exists(seq_file):
					continue

				# Read sequence file
				original_seqs = []
				for record in SeqIO.parse(seq_file, "fasta"):
					original_seqs.append((record.id, record.seq))

				# Skip if no sequences
				if not original_seqs:
					continue

				# Check each sequence length
				need_update = False
				for idx, (seq_id, seq) in enumerate(original_seqs):
					if len(seq) < self.seedLen:
						print(f"Warning: Sequence {seq_id} length ({len(seq)}bp) is shorter than set seed length ({self.seedLen}bp), will use entire sequence.")
						need_update = True

				# Continue to next file if no update needed
				if not need_update:
					continue

				# Create temporary file name
				temp_file = seq_file + ".temp"

				# Write new file
				with open(temp_file, 'w') as f:
					for seq_id, seq in original_seqs:
						f.write(f">{seq_id}\n{seq}\n")

				# Replace original file
				os.replace(temp_file, seq_file)
				print(f"Updated sequence file: {seq_file}")

		except Exception as e:
			print(f"Error checking and adjusting seed sequences: {e}")
			import traceback
			traceback.print_exc()

class Elongation(object):
	def __init__(self,base):
		self.base=base
		self.roundNum=1
		self.usedReads=[]
		self.extensionLen=0
		self.endSignal=False
		self.out=base.out
		self.resume_data = {}  # Store data needed for recovery
		self.has_direct_connection = False  # New: flag for direct connection existence
		self.direct_connection_result = None  # New: save direct connection result

		# Get MaximumExtensionRound from base object
		self.MaximumExtensionRound = getattr(self.base, 'MaximumExtensionRound', None)

		logfile=open(self.base.log,'w')
		summaryfile=open(self.base.summary,'w')

		# Initialize alignment tracking variables to avoid UnboundLocalError
		# These variables track alignment information from extension rounds
		atgInitial = ''   # Alignment info from first extension round
		atgTerminal = ''  # Alignment info from final extension round

		# Check if seqleft and seqright can be directly connected before starting extension
		self.check_direct_connection(logfile)

		# If need to continue from specific round
		if self.base.resume_round is not None:
			self.resume_from_checkpoint(self.base.resume_round)

		while self.endSignal==False and (self.MaximumExtensionRound is None or self.roundNum <= self.MaximumExtensionRound):
			self.ElongationInit(logfile)

			print(f"Starting round {self.roundNum}...")

			try:
				self.lastRoundUsedReads=self.ElongateSeq(logfile,summaryfile,self.lastRoundUsedReads,self.extensionLen)
				# ✨ 修复：添加 None 检查避免 AttributeError
				extension_reads_ok = self.roundResult.ExtensionReads is not None and self.roundResult.ExtensionReads.note == ''
				extension_contigs_ok = self.roundResult.ExtensionContigs is not None and 'No extension contigs or reads found' not in self.roundResult.ExtensionContigs.selectContigNote
				if extension_reads_ok and extension_contigs_ok:
					self.extensionLen=self.extensionLen+self.roundResult.ExtensionContigs.extensionLength
				if self.roundNum==1:
					if extension_reads_ok and extension_contigs_ok:
						atgInitial=self.roundResult.ExtensionContigs.selectExtensionContigsAln[0][0]
					else:
						atgInitial=''

				# Save checkpoint information after successful completion of current round
				print(f"Round {self.roundNum} completed successfully")
				self.base.save_checkpoint(self.roundNum)

			except Exception as e:
				# Record checkpoint when exception occurs - save the round that failed
				print(f"Round {self.roundNum} execution error: {str(e)}")
				print(f"Saving checkpoint for failed round: {self.roundNum}")
				self.base.save_checkpoint(self.roundNum)
				raise  # Re-raise exception for external handling

			self.roundNum+=1
			self.removeFile()
			
			# Memory cleanup after each round (skip for last round to preserve data for final result generation)
			if not self.endSignal and (self.MaximumExtensionRound is None or self.roundNum <= self.MaximumExtensionRound):
				self._cleanup_round_memory()
			
		summaryfile.close()

		# Check if stopped due to reaching maximum extension rounds
		if self.MaximumExtensionRound is not None and self.roundNum > self.MaximumExtensionRound and not self.endSignal:
			print(f"Reached maximum extension rounds: {self.MaximumExtensionRound}")
			logfile.write(f"\nReached maximum extension rounds: {self.MaximumExtensionRound}\n")
			logfile.write(f"Total rounds completed: {self.roundNum - 1}\n")
			logfile.write(f"Total extension length: {self.extensionLen} bp\n\n")
			# Mark as ended
			self.endSignal = True

		# Delete checkpoint file after completing all rounds
		if os.path.exists(self.base.checkpoint_file):
			os.remove(self.base.checkpoint_file)

		# Check if direct connection result should be used before generating final result
		use_direct_connection = False
		# Initialize default flag to avoid UnboundLocalError when extension output is missing
		process_log_negative = False
		
		# Check if direct connection result exists and should be used
		if self.has_direct_connection and self.direct_connection_result:
			logfile.write("\n========== Check if direct connection result should be used ==========\n")
			
			# Check if extension result can close gap
			extension_can_close_gap = False
			if hasattr(self, 'roundResult') and hasattr(self.roundResult, 'roundOutput'):
				if os.path.exists(self.roundDir+"/linkedSequence.fasta") and os.path.getsize(self.roundDir+"/linkedSequence.fasta") != 0:
					extension_can_close_gap = True
					
					# Further check if gap length is negative
					process_log_negative = False
					try:
						if os.path.exists(self.base.log):
							with open(self.base.log, 'r') as f:
								log_content = f.read()
								# Search for latest GAP Length record in log
								gap_length_matches = re.findall(r'GAP Length: ([-\d]+)', log_content)
								if gap_length_matches:
									last_gap_length = int(gap_length_matches[-1])
									if last_gap_length < 0:
										process_log_negative = True
										logfile.write(f"Detected negative GAP Length in extension phase: {last_gap_length}\n")
					except Exception as e:
						logfile.write(f"Error checking process.log: {str(e)}\n")
			
			# Decide whether to use direct connection result
			if not extension_can_close_gap or process_log_negative:
				use_direct_connection = True
				logfile.write("Decided to use direct connection result because:\n")
				if not extension_can_close_gap:
					logfile.write("- Extension phase failed to close gap\n")
				if process_log_negative:
					logfile.write("- Extension phase gap length is negative\n")
				
				# Use direct connection result
				logfile.write(f"Using direct connection result file: {self.direct_connection_result['final_seq_file']}\n")
				self.finalSeq = self.direct_connection_result['final_seq_file']
				
				# Create marker file indicating direct connection result was used
				with open(os.path.join(self.out, "USED_DIRECT_CONNECTION"), 'w') as f:
					f.write(f"Used direct connection result instead of extension result\n")
					f.write(f"Direct connection file: {self.direct_connection_result['final_seq_file']}\n")
					f.write(f"GAP Length: {self.direct_connection_result['gap_length']}\n")
					f.write(f"Overlap length: {self.direct_connection_result['overlap_length']}\n")
					f.write(f"Identity: {self.direct_connection_result['identity']}%\n")
			else:
				logfile.write("Extension phase successfully closed gap and gap length is not negative, using extension result\n")
			
			logfile.write("============================\n\n")
		
		self.roundNum=self.roundNum-1
		
		# If not using direct connection result, generate final result in original way
		if not use_direct_connection:
			self.finalSeq=self.base.out+'/'+self.base.name+'.final.fa'
			if os.path.exists(self.roundDir+"/linkedSequence.fasta")==True and  os.path.getsize(self.roundDir+"/linkedSequence.fasta")!=0:
				fileofs=open(self.finalSeq,'w')
				l='>'+self.base.name+"\n"
				fileofs.writelines(l)
				for gseq in SeqIO.parse(self.roundResult.roundOutput.linkedSequence,'fasta'):
					l0=gseq.description
					l1=l0.split('\t')
					l=str(gseq.seq)+'\n'
					fileofs.writelines(l)
					for l11 in l1:
						l2=l11.split(':')
						if l2[0]=="Aln":
							atgTerminal=l2[1]
				fileofs.close()
			elif (self.roundResult.ExtensionReads is not None and self.roundResult.ExtensionReads.note!='') or (self.roundResult.ExtensionContigs is not None and ('No extension contigs or reads found' in self.roundResult.ExtensionContigs.selectContigNote or "Reach the maximum Length" in self.roundResult.ExtensionContigs.selectContigNote)):
				fileofs=open(self.finalSeq,'w')
				extension_reads_note = self.roundResult.ExtensionReads.note if self.roundResult.ExtensionReads is not None else ''
				extension_contigs_note = self.roundResult.ExtensionContigs.selectContigNote if self.roundResult.ExtensionContigs is not None else ''
				if extension_reads_note=='':
					if 'Reach the maximum Length' in extension_contigs_note:
						l='>'+self.base.name+"_reachMaximumLength\n"
					else:
						l='>'+self.base.name+"_noExtensionContigsorReads\n"
				else:
					l='>'+self.base.name+"_noExtensionContigsorReads\n"
				fileofs.writelines(l)
				atgTerminal=''
				for gseq in SeqIO.parse(self.roundInputSeq,'fasta'):
					l=str(gseq.seq)+'\n'
					fileofs.writelines(l)
				fileofs.close()
			else:
				fileofs=open(self.finalSeq,'w')
				l='>'+self.base.name+"_noNewExtensionReads\n"
				fileofs.writelines(l)
				atgTerminal=''
				for gseq in SeqIO.parse(self.roundResult.roundOutput.outputSequence,'fasta'):
					l=str(gseq.seq)+'\n'
					fileofs.writelines(l)
				fileofs.close()
		
		# If --remove=1 is set, ensure final result file won't be deleted
		if self.base.remove == 1:
			# Ensure final result file has been generated and has content
			if os.path.exists(self.finalSeq) and os.path.getsize(self.finalSeq) > 0:
				print(f"Generated final result file: {self.finalSeq}")

				# Copy important log files to safe location
				import shutil
				log_backup = self.base.out + '/process.log.backup'
				summary_backup = self.base.out + '/process.summary.backup'
				agp_backup = self.base.out + '/process.agp.backup'

				if os.path.exists(self.base.log):
					shutil.copy2(self.base.log, log_backup)
				if os.path.exists(self.base.summary):
					shutil.copy2(self.base.summary, summary_backup)
				if os.path.exists(self.base.agp):
					shutil.copy2(self.base.agp, agp_backup)

				print("Backed up important log files")
	
		for fgseq in SeqIO.parse(self.finalSeq,'fasta'):
			l='Final ExtensionSequence: '+fgseq.id+"\n"
			l=l+'Final EXtendFile: '+self.finalSeq+"\n"
			logfile.writelines(l)
		logfile.close()
		
		agpfile=open(self.base.agp,'w')
		for gseq in SeqIO.parse(self.base.initialSeq,'fasta'):
			initialSequence=gseq
		if atgInitial!='':
			if self.base.flag=='left':
				atgInitial1=atgInitial.split('\t')
				st=len(initialSequence.seq)-(int(atgInitial1[7])-int(atgInitial1[1]))
				if atgTerminal=='':
					l=self.base.name+"\t1"+"\t"+str(st)+"\t1\tw\t"+initialSequence.id+"\t1\t"+str(st)+"\t+\n"
					agpfile.writelines(l)
					l=self.base.name+"\t"+str(st+1)+"\t"+str(len(fgseq.seq))+"\t2\tw\t"+fgseq.id+"\t"+str(st+1)+"\t"+str(len(fgseq.seq))+"\t+\n"
					agpfile.writelines(l)
					self.TerminalSeq=None
				else:
					l=self.base.name+"\t1"+"\t"+str(st)+"\t1\tw\t"+initialSequence.id+"\t1\t"+str(st)+"\t+\n"
					agpfile.writelines(l)
					atgTerminal1=atgTerminal.split(';')
					eT=len(fgseq.seq)-(int(atgTerminal1[7])-int(atgTerminal1[4]))
					l=self.base.name+"\t"+str(st+1)+"\t"+str(eT)+"\t2\tw\t"+fgseq.id+"\t"+str(st+1)+"\t"+str(eT)+"\t+\n"
					agpfile.writelines(l)
					Terminalname1=atgTerminal1[-2]
					l=self.base.name+"\t"+str(int(eT)+1)+"\t"+str(len(fgseq.seq))+"\t3\tw\t"+Terminalname1+"\t"+str(int(atgTerminal1[1])+1)+"\t"+atgTerminal1[7]+"\t+\n"
					agpfile.writelines(l)
					self.TerminalSeq=Terminalname1
		
			else:
				atgInitial1=atgInitial.split('\t')
				st=len(fgseq.seq)-len(initialSequence.seq)+int(atgInitial1[0])-1
				if atgTerminal=='':
					atgInitial1=atgInitial.split('\t')
					l=self.base.name+"\t1\t"+str(st)+"\t1\tw\t"+fgseq.id+"\t1\t"+str(st)+"\t+\n"
					agpfile.writelines(l)
					l=self.base.name+"\t"+str(st+1)+"\t"+str(len(fgseq))+"\t2\tw\t"+initialSequence.id+"\t"+atgInitial1[0]+"\t"+str(len(initialSequence.seq))+"\t+\n"
					agpfile.writelines(l)
					self.TerminalSeq=None
					
				else:
					atgTerminal1=atgTerminal.split(';')
					atgInitial1=atgInitial.split('\t')
					sT=int(atgTerminal1[1])
					l=self.base.name+"\t1\t"+str(sT)+"\t1\tw\t"+atgTerminal1[-2]+"\t1\t"+atgTerminal1[1]+"\t+\n"
					agpfile.writelines(l)
					l=self.base.name+"\t"+str(sT+1)+"\t"+str(st)+"\t2\tw\t"+fgseq.id+"\t"+str(sT+1)+"\t"+str(st)+"\t+\n"
					agpfile.writelines(l)
					l=self.base.name+"\t"+str(st+1)+"\t"+str(len(fgseq))+"\t3\tw\t"+initialSequence.id+"\t1\t"+atgTerminal1[1]+"\t+\n"
					agpfile.writelines(l)
					self.TerminalSeq=atgTerminal1[-2]
		else:
			l=self.base.name+"\t1"+"\t"+str(len(initialSequence.seq))+"\t1\tw\t"+initialSequence.id+"\t1\t"+str(len(initialSequence.seq))+"\t+\n"
			agpfile.writelines(l)
		agpfile.close()
		self.removeFile()
				
	def removeFile(self):
		if os.path.exists(self.roundDir+"/hifiasm")==True or os.path.exists(self.roundDir+"/potentialExtensionReads.left.sam")==True:
			if self.base.remove==2 or self.base.remove==1:
				commondline='rm '+self.roundDir+"/*.bam"
				os.system(commondline)
				commondline='rm -rf '+self.roundDir+"/hifiasm"
				os.system(commondline)
		if self.endSignal==True:
			if os.path.exists(self.base.outfile)==True:
				if self.base.remove==1:
					# Modified: Don't delete entire output directory immediately, clean up after all processing is complete
					# First save final result file
					final_seq = self.base.out+'/'+self.base.name+'.final.fa'
					if os.path.exists(final_seq):
						# Ensure final result file has been generated
						print(f"Keeping final result file: {final_seq}")
					else:
						print(f"Warning: Final result file not yet generated, skipping output directory cleanup")
						return

					# Only delete intermediate process files, keep final results
					for root, dirs, files in os.walk(self.base.outfile):
						for file in files:
							file_path = os.path.join(root, file)
							os.remove(file_path)

					# Don't delete directory structure, only delete files
					print(f"Cleaned up intermediate process files, kept final results and directory structure")

	def _cleanup_round_memory(self):
		"""Clean up memory after each round to prevent memory accumulation"""
		import gc
		
		# Clear previous round's result if exists
		if hasattr(self, 'roundResult') and self.roundResult is not None:
			# Clear ExtensionReads large data structures
			if hasattr(self.roundResult, 'ExtensionReads') and self.roundResult.ExtensionReads is not None:
				er = self.roundResult.ExtensionReads
				# Clear all large lists
				for attr in ['minimumThresholdReadsID', 'minimumThresholdExtensionReadsID', 
				             'selectPotentialExtensionReadsID', 'extensionReadsID',
				             'potentialExtensionReadsID', 'selectExtensionReadsID',
				             'potentialExtensionReadsAln', 'selectPotentialExtensionReadsAln',
				             'extensionReadsAln', 'kmerFilteredReadsID']:
					if hasattr(er, attr):
						setattr(er, attr, [])
				# Clear dictionaries
				for attr in ['readsDict', 'kmerCountDict']:
					if hasattr(er, attr):
						setattr(er, attr, {})
				# Clear roundInput reference
				if hasattr(er, 'roundInput'):
					er.roundInput = None
			
			# Clear ExtensionContigs large data structures
			if hasattr(self.roundResult, 'ExtensionContigs') and self.roundResult.ExtensionContigs is not None:
				ec = self.roundResult.ExtensionContigs
				# Clear hifiasm result dict and other large structures
				for attr in ['hifiasmResultDict', 'contigDict', 'readsDict']:
					if hasattr(ec, attr):
						setattr(ec, attr, {})
				for attr in ['selectExtensionContigsAln', 'extensionContigID', 'contigAlnList']:
					if hasattr(ec, attr):
						setattr(ec, attr, [])
				# Clear sequence data
				if hasattr(ec, 'extensionSequence'):
					ec.extensionSequence = None
			
			# Clear roundInput (InputSequence object)
			if hasattr(self.roundResult, 'roundInput') and self.roundResult.roundInput is not None:
				ri = self.roundResult.roundInput
				if hasattr(ri, 'inputSeedSequence'):
					ri.inputSeedSequence = None
				if hasattr(ri, 'elongation'):
					ri.elongation = None
				self.roundResult.roundInput = None
			
			# Clear roundOutput (OutputSequence object)
			if hasattr(self.roundResult, 'roundOutput') and self.roundResult.roundOutput is not None:
				ro = self.roundResult.roundOutput
				for attr in ['ExtensionUsedReads', 'linkedSequenceNote']:
					if hasattr(ro, attr):
						if isinstance(getattr(ro, attr), list):
							setattr(ro, attr, [])
						else:
							setattr(ro, attr, '')
				if hasattr(ro, 'extensionContigs'):
					ro.extensionContigs = None
				if hasattr(ro, 'Elongation'):
					ro.Elongation = None
				self.roundResult.roundOutput = None
			
			# Clear references in roundResult
			self.roundResult.ExtensionReads = None
			self.roundResult.ExtensionContigs = None
			self.roundResult.Elongation = None
		
		# Force garbage collection
		gc.collect()
		print(f"[Memory] Cleaned up round {self.roundNum} memory")

	def ElongateSeq(self,logfile,summaryfile,lastRoundUsedReads,extensionLen):
		self.lastRoundUsedReads=lastRoundUsedReads
		roundLog=open(self.roundLog,'w')
		roundSummary=open(self.roundSummary,'w')
		self.roundResult=GapFillerClass(self,out=self.out)
		print ("MaximunExtensionLength",self.base.MaximunExtensionLength,"TotalExtensionLength",extensionLen)
		#sys.exit()
		if self.base.MaximunExtensionLength!=None:
			if extensionLen>self.base.MaximunExtensionLength: #Max
				#print (self.roundResult.ExtensionContigs.extensionLength,self.base.MaximunExtensionLength,"MaximunExtensionLength")
				self.roundResult.ExtensionContigs.selectContigNote=self.roundResult.ExtensionContigs.selectContigNote+"Reach the maximum Length\n"
				print (self.roundResult.ExtensionContigs.selectContigNote)
				#sys.exit()
		logLine,summeryLine=self.writelog(extensionLen)
		print (logLine)
		roundLog.writelines(logLine)
		roundSummary.writelines(summeryLine)
		logfile.writelines(logLine)
		summaryfile.writelines(summeryLine)
		roundLog.close()
		roundSummary.close()
		# ✨ 修复：添加 None 检查
		extension_reads_ok = self.roundResult.ExtensionReads is not None and self.roundResult.ExtensionReads.note == ''
		extension_contigs_ok = self.roundResult.ExtensionContigs is not None and 'No extension contigs or reads found' not in self.roundResult.ExtensionContigs.selectContigNote and "Reach the maximum Length" not in self.roundResult.ExtensionContigs.selectContigNote
		if extension_reads_ok and extension_contigs_ok:
			return self.roundResult.roundOutput.ExtensionUsedReads
		else:
			return []
	
	def writelog(self,extensionLen):
		logLine='\n\n*****************\n\n'
		logLine+='\toutputPath: '+str(self.roundDir)+"\n"
		logLine+="\thifiSeedSequenceLength: "+str(self.base.hifiSeedLen)+"\n"
		logLine+="\tontSeedSequenceLength: "+str(self.base.ontSeedLen)+"\n"
		logLine+="\tseedSequenceLength: "+str(self.base.seedLen)+" (primary)\n"
		logLine+="\tinitialSequenceFile: "+str(self.base.initialSeq)+"\n"
		inputSeq = None
		for gseq in SeqIO.parse(self.roundInputSeq,'fasta'):
			inputSeq=gseq
		if inputSeq is not None:
			logLine+="\t\tinitialSeqnenceID: "+str(inputSeq.id)+"\n\t\tinitialSeqnenceLength: "+str(len(inputSeq.seq))+"\n"
		else:
			logLine+="\t\tinitialSeqnenceID: N/A (no sequence found)\n\t\tinitialSeqnenceLength: 0\n"
		logLine+="\tterminalSequenceFile: "+str(self.base.terminalSeq)+"\n"
		logLine+="\tseedSequenceFile: "+str(self.roundResult.roundInput.inputSeq)+"\n"
		logLine+="\t\tseedSeqnenceID: "+str(self.roundResult.roundInput.inputSeedSequence.id)+"\n\t\tseedSeqnenceLength: "+str(len(self.roundResult.roundInput.inputSeedSequence.seq))+"\n\n"
		# ✨ 修复：添加 None 检查
		extension_reads_ok = self.roundResult.ExtensionReads is not None and self.roundResult.ExtensionReads.note == ''
		extension_contigs_ok = self.roundResult.ExtensionContigs is not None and 'No extension contigs or reads found' not in self.roundResult.ExtensionContigs.selectContigNote and "Reach the maximum Length" not in self.roundResult.ExtensionContigs.selectContigNote
		if extension_reads_ok and extension_contigs_ok:
			logLine+='minimap2Commond: '+str(self.roundResult.ExtensionReads.minimap2Command)+"\n"
			logLine+='\textensionReads: \n\tselectReadsNum: '+str(self.roundResult.ExtensionReads.selectReadsNum)+"\n"
			logLine+="\t\tselectReadsAln: "+str(self.roundResult.ExtensionReads.selectPotentialExtensionReadsAln)+"\n"
			logLine+="\t\tselectMappingQuality: "+str(self.roundResult.ExtensionReads.selectMappingQuality)+"\n"
			logLine+="\t\tselectAlignmentLength: "+str(self.roundResult.ExtensionReads.selectAlignmentLength)+"\n"
			logLine+="\t\tselectNMAlignmentLengthratio: "+str(self.roundResult.ExtensionReads.selectNMAlignmentLengthratio)+"\n\n"
			logLine+="\textensionReadsNum: "+str(self.roundResult.ExtensionReads.extensionReadsNum)+"\n"
			logLine+="\t\textensionReadsAln: "+str(self.roundResult.ExtensionReads.extensionReadsAln)+"\n"
			logLine+="\t\textensionReadsFile: "+str(self.roundResult.ExtensionReads.extensionReads)+"\n"
			logLine+="\t\textensionReadsMinimumExtensionLength: "+str(self.roundResult.ExtensionReads.readsExtensionLength)+"\n"
			logLine+="\t\textensionReadsMaximumEdge: "+str(self.roundResult.ExtensionReads.extensionReadsEdge)+"\n\n"

			logLine+="\textensionSequnece: "+str(self.roundResult.ExtensionContigs.extensionContigs)+"\n"
			logLine+="\textensionSequneceNote: "+str(self.roundResult.ExtensionContigs.extensionSeqNote)+"\n"+str(self.roundResult.ExtensionContigs.selectContigNote)+"\n"
			logLine+="\t\textensionSequneceIdentity: "+str(self.roundResult.ExtensionContigs.selectContigIdentity)+"\n"
			logLine+="\t\textensionSequneceMinimumExtensionLength: "+str(self.roundResult.ExtensionContigs.selectContigAlnLength)+"\n"
			logLine+="\t\textensionSequneceMaximumEdge: "+str(self.roundResult.ExtensionContigs.selectContigDistance)+"\n"
			logLine+="\t\textensionSequneceAlnMerge: "+str(self.roundResult.ExtensionContigs.contigAlnMerge)+"\n"
			logLine+="\t\textensionSequneceAlnMergeIdentity: "+str(self.roundResult.ExtensionContigs.contigAlnMergeIdentity)+"\n"
			logLine+="\textensionSeedSequenceFile: "+str(self.roundResult.ExtensionContigs.extensionSequence)+"\n"
			logLine+="\textensionLength: "+str(self.roundResult.ExtensionContigs.extensionLength)+"\n"
			logLine+="\t\textensionContigOrReadsID:\n\t\t\t"+'\n\t\t\t'.join(self.roundResult.ExtensionContigs.extensionContigID)+"\n"
			newReads,note=self.updateUsedReads()
			logLine+=note
			
			# Check if self.roundResult has roundOutput attribute
			if hasattr(self.roundResult, 'roundOutput'):
				logLine+="\t\tusedReadsNum: "+str(len(self.roundResult.roundOutput.ExtensionUsedReads))+"\n"
				logLine+="\t\tusedReads:\n\t\t\t"+"\n\t\t\t".join(self.roundResult.roundOutput.ExtensionUsedReads)+"\n"
				logLine+="\t\tusedNewReads:\n\t\t\t"+"\n\t\t\t".join(newReads)+"\n\n"
				logLine+="\toutputFile: "+str(self.roundResult.roundOutput.outputSequence)+"\n"
				logLine+="\t\toutputSequenceLength: "+str(self.roundResult.roundOutput.totalOutputSequenceLength)+"\n\n"
				logLine+="\t\ttotalExtensionLength: "+str(extensionLen)+"\n\n"
				
				if self.roundResult.roundOutput.linkedSequenceNote!='':
					logLine+='\tGAP can be closed!\n'+str(self.roundResult.roundOutput.linkedSequenceNote)+"\nLinkedSequence File: "+str(self.roundResult.roundOutput.linkedSequence)+"\n"
					logLine+='Endloop!\t'+str(self.roundResult.roundOutput.linkedSequence)+"\n"
					for gseq in SeqIO.parse(self.roundResult.roundOutput.linkedSequence,'fasta'):
						l0=gseq.description
						l1=l0.split('\t')
						for l11 in l1:
							l2=l11.split(':')
							if l2[0]=="Aln":
								closectg=l2[1].split(';')
								logLine+="Linked ctg:\t"+closectg[-2]+"\n"
								logLine+='\t'.join(closectg)+"\n"
							self.endSignal=True
				else:
					logLine+='\tGAP still not closed!\n'
			else:
				# If no roundOutput attribute, add appropriate information
				logLine+="\t\tNo output sequence generated in this round.\n"
				logLine+="\t\ttotalExtensionLength: "+str(extensionLen)+"\n\n"
				logLine+='\tGAP could not be processed further - missing output information.\n'
				self.endSignal=True
			
			logLine+='\n\n*****************\n\n'
			summeryLine='round'+str(self.roundNum)+"\t"+str(len(inputSeq.seq))+"\t"
			
			# Also check roundOutput attribute to correctly generate summary line
			if hasattr(self.roundResult, 'roundOutput'):
				summeryLine+=str(self.roundResult.roundOutput.totalOutputSequenceLength)+"\t"+str(self.roundResult.ExtensionContigs.extensionLength)+"\t"+"-ovl-".join(self.roundResult.ExtensionContigs.extensionContigID)+"\t"+str(len(newReads))+"\t"+";".join(newReads)+"\t"+str(len(self.roundResult.roundOutput.ExtensionUsedReads))+"\t"+";".join(self.roundResult.roundOutput.ExtensionUsedReads)+"\n"
			else:
				summeryLine+="0\t0\tno_extension\t0\tnone\t0\tnone\n"
			
			return logLine,summeryLine
		else:
			# ✨ 修复：添加 None 检查
			extension_reads_note = self.roundResult.ExtensionReads.note if self.roundResult.ExtensionReads is not None else ''
			extension_contigs_note = self.roundResult.ExtensionContigs.selectContigNote if self.roundResult.ExtensionContigs is not None else ''
			
			if extension_reads_note != '':
				# Check if this is the specific "no extension reads" condition
				if 'noExtensionReadsFoundAtMinimumThreshold' in extension_reads_note or 'noExtensionReadsFoundAfterParameterRelaxation' in extension_reads_note:
					logLine+='No Extension Reads Found - Normal Completion\n'
					logLine+="\n\tThis is a normal completion condition. The gap filling process has reached a natural stopping point.\n"
					logLine+="\tPossible reasons:\n"
					logLine+="\t1. The gap region may not have sufficient read coverage for extension.\n"
					logLine+="\t2. The current assembly has reached the maximum possible extension with available data.\n"
					logLine+="\t3. The gap may be in a repetitive or complex region that requires different approaches.\n\n"
					logLine+="\tAssembly results can be found at: "+self.base.out+'/'+self.base.name+'.final.fa'+"\n\n"
					logLine+="\tIf you want to try different parameters, consider adjusting:\n"
					logLine+="\t--kmer_size (current: default), --kmer_num (current: default), --edge (current: default)\n\n"
				else:
					logLine+='No ExtensionReads or ExtensionContig Found\n'
					logLine+="\n\tPossible reason 1: Your original data can only support assembly up to the current length. Assembly results can be found at: "+self.base.out+'/'+self.base.name+'.final.fa'+"\n\n"
					logLine+="\tPossible reason 2: There may be an issue with the kmer filtering parameters. The current default parameters for kmer filtering are: --kmer_size 41, --kmer_num 4. "
					logLine+="This parameter combination is based on rice HiFi sequencing data. "
					logLine+="If you are using it to assemble other species' genomes, you can set appropriate parameters through --kmer_size and --kmer_num.\n\n"
			else:
				if "Reach the maximum Length" not in extension_contigs_note:
					logLine+='No ExtensionReads or ExtensionContig Found\n'
				else:
					logLine+='Reach the maximum Length\n'
			logLine+="Endloop!\t"+extension_reads_note+"\n"
			logLine+="\t\ttotalExtensionLength: "+str(extensionLen)+"\n\n"
			self.endSignal=True
			summeryLine=''
			return logLine,summeryLine

	def updateUsedReads(self):
		newReads=[]
		sameWithLastRound=[]
		note=''
		for i1 in self.roundResult.roundOutput.ExtensionUsedReads:
			if i1 not in self.usedReads:
				self.usedReads.append(i1)
				newReads.append(i1)
			if i1 in self.lastRoundUsedReads:
				sameWithLastRound.append(i1)
		if len(newReads)==0 :
			note='No New ExtensionReads Found,\t'
			if len(sameWithLastRound)==0:
				note+='Not same ExtensionReads with last round ExtensionReads, end up a loop!!\n'
				self.endSignal=True
			else:
				note+='Same ExtensionReads with the last round,continune the loop!\n'
				# ✨ 修复：添加 None 检查
				extension_length = self.roundResult.ExtensionContigs.extensionLength if self.roundResult.ExtensionContigs is not None else 0
				if extension_length == 0:
					note+='However,ExtensionLength==0,end up a loop!!\n'
					self.endSignal=True
		return newReads,note

	
	def ElongationInit(self,logfile):
		l='\n\n*****************\n\nExtensionRound '+str(self.roundNum)+'\n'
		logfile.writelines(l)
		print (l)
		self.roundDir=self.base.outfile+'/round'+str(self.roundNum)
		if not os.path.exists(self.roundDir):
			os.makedirs(self.roundDir)
		self.lastRoundDir=self.base.outfile+'/round'+str(self.roundNum-1)
		self.roundLog=self.base.outfile+'/round'+str(self.roundNum)+"/log"
		self.roundSummary=self.base.outfile+'/round'+str(self.roundNum)+"/summary"

		if self.roundNum!=1:
			self.roundInputSeq=self.lastRoundDir+'/outputExtensionSequence.fasta'
			# Check updated seed sequence
			self.check_seed_sequence_length()
		else:
			self.roundInputSeq=self.base.initialSeq
			self.lastRoundUsedReads=[]

	def check_seed_sequence_length(self):
		"""Check seed sequence length in each iteration, use entire sequence if shorter than seedLen"""
		try:
			if not os.path.exists(self.roundInputSeq):
				print(f"Warning: Cannot find seed sequence file {self.roundInputSeq}")
				return

			# Read sequence file
			original_seqs = []
			for record in SeqIO.parse(self.roundInputSeq, "fasta"):
				original_seqs.append((record.id, record.seq))

			# Return if no sequences
			if not original_seqs:
				print(f"Warning: No sequences in seed sequence file {self.roundInputSeq}")
				return

			# Check each sequence length
			need_update = False
			for idx, (seq_id, seq) in enumerate(original_seqs):
				if len(seq) < self.base.seedLen:
					print(f"Round {self.roundNum}: Sequence {seq_id} length ({len(seq)}bp) is shorter than set seed length ({self.base.seedLen}bp), will use entire sequence.")
					need_update = True

			# Return directly if no update needed
			if not need_update:
				return

			# Create temporary file name
			temp_file = self.roundInputSeq + ".temp"

			# Write new file
			with open(temp_file, 'w') as f:
				for seq_id, seq in original_seqs:
					f.write(f">{seq_id}\n{seq}\n")

			# Replace original file
			os.replace(temp_file, self.roundInputSeq)
			print(f"Updated seed sequence file: {self.roundInputSeq}")

		except Exception as e:
			print(f"Error checking seed sequence length: {e}")
			import traceback
			traceback.print_exc()

	def resume_from_checkpoint(self, target_round):
		"""Resume execution state from specified round"""
		print(f"Preparing to resume execution from round{target_round}...")

		# Set initial round to target round
		self.roundNum = target_round

		# Determine previous round directory
		last_round = target_round - 1
		if last_round > 0:
			self.lastRoundDir = self.base.outfile+'/round'+str(last_round)
			
			# Read previous round's output sequence as input for this round
			self.roundInputSeq = self.lastRoundDir+'/outputExtensionSequence.fasta'

			# If previous round's output sequence doesn't exist, use original sequence
			if not os.path.exists(self.roundInputSeq):
				print(f"Warning: Cannot find previous round's output sequence {self.roundInputSeq}, will use initial sequence")
				self.roundInputSeq = self.base.initialSeq
				self.lastRoundUsedReads = []
			else:
				# Try to recover used reads information from previous round's summary file
				summary_file = self.lastRoundDir+"/summary"
				self.lastRoundUsedReads = []
				self.usedReads = []

				if os.path.exists(summary_file):
					try:
						with open(summary_file, 'r') as f:
							last_line = f.readlines()[-1].strip()
							if last_line:
								fields = last_line.split('\t')
								if len(fields) >= 9:  # Ensure sufficient fields
									self.lastRoundUsedReads = fields[8].split(';') if fields[8] != 'none' else []
									self.usedReads = self.lastRoundUsedReads.copy()
					except Exception as e:
						print(f"Failed to recover reads information from summary file: {e}")
						self.lastRoundUsedReads = []
						
				# Try to read previous round's extension length
				logs_file = self.lastRoundDir+"/log"
				if os.path.exists(logs_file):
					try:
						with open(logs_file, 'r') as f:
							content = f.read()
							extension_matches = re.findall(r'totalExtensionLength:\s+(\d+)', content)
							if extension_matches:
								self.extensionLen = int(extension_matches[-1])
								print(f"Recovered current extension length from log file: {self.extensionLen}")
					except Exception as e:
						print(f"Failed to recover extension length from log file: {e}")
						# If unable to recover extension length, try to calculate
						try:
							initial_seq_len = 0
							for gseq in SeqIO.parse(self.base.initialSeq,'fasta'):
								initial_seq_len = len(gseq.seq)

							current_seq_len = 0
							for gseq in SeqIO.parse(self.roundInputSeq,'fasta'):
								current_seq_len = len(gseq.seq)

							self.extensionLen = current_seq_len - initial_seq_len
							if self.extensionLen < 0:
								self.extensionLen = 0
							print(f"Calculated extension length: {self.extensionLen}")
						except Exception as calc_e:
							print(f"Failed to calculate extension length: {calc_e}")
							self.extensionLen = 0
		else:
			# If first round, use initial settings
			self.roundInputSeq = self.base.initialSeq
			self.lastRoundUsedReads = []

		print(f"Ready to continue execution from round{target_round}, current extension length: {self.extensionLen}")

	def check_direct_connection(self, logfile):
		"""Check if seqleft and seqright can be directly connected (including tandem repeats and normal overlaps)
		
		支持两种模式：
		1. 单序列 vs 单序列：传统GapFiller模式
		2. 单序列(seed) vs 多序列(edge库)：CtgLinker模式，遍历所有edge检查直连
		"""
		import tempfile
		import os

		logfile.write("\n========== Direct Connection Check ==========\n")

		# Check if files exist
		if not os.path.exists(self.base.seqleft) or not os.path.exists(self.base.seqright):
			logfile.write("Cannot check direct connection: left or right sequence file does not exist\n")
			logfile.write("============================\n\n")
			return

		# 读取所有序列
		left_records = list(SeqIO.parse(self.base.seqleft, "fasta"))
		right_records = list(SeqIO.parse(self.base.seqright, "fasta"))

		if not left_records or not right_records:
			logfile.write("Cannot check direct connection: left or right sequence is empty\n")
			logfile.write("============================\n\n")
			return

		logfile.write(f"Left file sequences: {len(left_records)}\n")
		logfile.write(f"Right file sequences: {len(right_records)}\n")

		# 确定是否为CtgLinker模式（通过检查文件名中是否包含ctgsEdge）
		is_ctglinker_mode = ('ctgsEdge' in self.base.seqleft or 'ctgsEdge' in self.base.seqright)
		
		# 只有CtgLinker模式才遍历多序列edge库
		if is_ctglinker_mode and len(left_records) == 1 and len(right_records) > 1:
			# seqleft是seed，seqright是edge库
			seed_record = left_records[0]
			edge_records = right_records
			seed_is_left = True
			logfile.write(f"Mode: CtgLinker - seed (left) vs edge library (right, {len(edge_records)} edges)\n")
		elif is_ctglinker_mode and len(right_records) == 1 and len(left_records) > 1:
			# seqright是seed，seqleft是edge库
			seed_record = right_records[0]
			edge_records = left_records
			seed_is_left = False
			logfile.write(f"Mode: CtgLinker - edge library (left, {len(edge_records)} edges) vs seed (right)\n")
		else:
			# 传统模式（GapFiller/TelSeeker等）：只检查第一条序列
			seed_record = left_records[0]
			edge_records = [right_records[0]]
			seed_is_left = True
			logfile.write(f"Mode: single sequence vs single sequence (traditional)\n")
			# 记录原始序列长度（与 GapfillerVisualizer 解析格式兼容）
			logfile.write(f"Original left sequence length: {len(left_records[0].seq)}bp\n")
			logfile.write(f"Original right sequence length: {len(right_records[0].seq)}bp\n")

		seed_seq = seed_record.seq
		seed_id = seed_record.id
		logfile.write(f"Seed sequence: {seed_id}, length: {len(seed_seq)}bp\n")

		# Extract seed-length fragments based on position
		# 直连检查始终比较: seqleft的RIGHT端 vs seqright的LEFT端
		# 不管flag是什么，因为gap永远在seqleft右边、seqright左边
		seed_len = int(self.base.seedLen)
		logfile.write(f"Using seed length: {seed_len}bp\n")

		# 提取片段：seqleft取RIGHT端，seqright取LEFT端
		if seed_is_left:
			# seed是seqleft → 取seed的RIGHT端
			seed_fragment = seed_seq[-seed_len:] if len(seed_seq) >= seed_len else seed_seq
			logfile.write(f"Seed is seqleft: extracting RIGHT {len(seed_fragment)}bp from seed\n")
		else:
			# seed是seqright → 取seed的LEFT端
			seed_fragment = seed_seq[:seed_len] if len(seed_seq) >= seed_len else seed_seq
			logfile.write(f"Seed is seqright: extracting LEFT {len(seed_fragment)}bp from seed\n")

		# Create temporary directory for mummer analysis
		temp_dir = os.path.join(self.out, "direct_connection_check")
		os.makedirs(temp_dir, exist_ok=True)

		# 写入seed片段
		seed_file = os.path.join(temp_dir, "seed.fasta")
		with open(seed_file, "w") as f:
			f.write(f">{seed_id}_fragment\n{seed_fragment}\n")

		# 遍历所有edge序列检查直连
		all_qualifying_overlaps = []
		edge_threshold = self.base.edge if hasattr(self.base, 'edge') and self.base.edge else 500

		logfile.write(f"\nChecking {len(edge_records)} edge sequence(s)...\n")
		logfile.write(f"Edge threshold: {edge_threshold}bp\n\n")

		for edge_idx, edge_record in enumerate(edge_records):
			edge_seq = edge_record.seq
			edge_id = edge_record.id

			# 提取edge片段：seqleft取RIGHT端，seqright取LEFT端
			if seed_is_left:
				# seed是seqleft，edge是seqright → edge取LEFT端
				edge_fragment = edge_seq[:seed_len] if len(edge_seq) >= seed_len else edge_seq
			else:
				# seed是seqright，edge是seqleft → edge取RIGHT端
				edge_fragment = edge_seq[-seed_len:] if len(edge_seq) >= seed_len else edge_seq

			# 写入edge片段
			edge_file = os.path.join(temp_dir, "edge.fasta")
			with open(edge_file, "w") as f:
				f.write(f">{edge_id}_fragment\n{edge_fragment}\n")

			# 根据seed位置确定mummer比对顺序
			if seed_is_left:
				left_file, right_file = seed_file, edge_file
				left_fragment, right_fragment = seed_fragment, edge_fragment
			else:
				left_file, right_file = edge_file, seed_file
				left_fragment, right_fragment = edge_fragment, seed_fragment

			# Use mummer for alignment
			mummer_prefix = os.path.join(temp_dir, f"direct_connection_{edge_idx}")
			mummer_output = mummer(left_file, right_file, mummer_prefix)

			# Analyze alignment results
			if os.path.exists(mummer_output) and os.path.getsize(mummer_output) > 0:
				with open(mummer_output, "r") as f:
					for line in f:
						if line.startswith("#"):
							continue
						parts = line.strip().split("\t")
						if len(parts) < 10:
							continue

						try:
							s1, e1, s2, e2 = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
							length = int(parts[4])
							identity = float(parts[6])

							len_left_fragment = len(left_fragment)
							len_right_fragment = len(right_fragment)

							left_distance_to_edge = len_left_fragment - e1
							right_distance_to_edge = s2 - 1

							meets_position_requirement = (left_distance_to_edge <= edge_threshold and
							                             right_distance_to_edge <= edge_threshold)
							meets_length_requirement = length >= 10000
							meets_identity_requirement = identity >= 80.0

							if meets_position_requirement and meets_length_requirement and meets_identity_requirement:
								all_qualifying_overlaps.append({
									's1': s1, 'e1': e1, 's2': s2, 'e2': e2,
									'length': length, 'identity': identity,
									'edge_id': edge_id, 'edge_seq': edge_seq,
									'seed_is_left': seed_is_left,
									'parts': parts
								})
								logfile.write(f"[Edge {edge_idx+1}/{len(edge_records)}] {edge_id}: MATCH\n")
								logfile.write(f"  Alignment: {s1}-{e1} vs {s2}-{e2}, length={length}bp, identity={identity}%\n")
								logfile.write(f"  Edge distances: left={left_distance_to_edge}, right={right_distance_to_edge}\n")
						except ValueError:
							continue

		logfile.write(f"\nTotal qualifying alignments: {len(all_qualifying_overlaps)}\n")

		# Process qualifying alignments if they exist
		if all_qualifying_overlaps:
			# Sort by overlap length and identity, select the best one
			best = sorted(all_qualifying_overlaps, key=lambda x: (x['length'], x['identity']), reverse=True)[0]

			s1, e1, s2, e2 = best['s1'], best['e1'], best['s2'], best['e2']
			length, identity = best['length'], best['identity']
			edge_id, edge_seq = best['edge_id'], best['edge_seq']
			seed_is_left = best['seed_is_left']

			gap_length = -(length)

			# Build final sequence
			# edge_seq 现在是完整 contig，使用 overlap length 来裁剪
			if seed_is_left:
				# seed在左，edge(完整contig)在右
				# edge的左端与seed右端overlap → 跳过edge左端的overlap部分
				final_seq = str(seed_seq) + str(edge_seq[length:])
			else:
				# seed在右，edge(完整contig)在左
				# edge的右端与seed左端overlap → 去掉edge右端的overlap部分
				final_seq = str(edge_seq[:-length]) + str(seed_seq)

			# Create final result file
			direct_connection_final = os.path.join(self.base.out, f"{self.base.name}.direct.final.fa")

			# 构建与延伸结果兼容的 header，包含 Aln 信息供 CtgLinker 解析
			# 格式: >name_direct_overlap\tgap:N\tlen:N\tAln:s1;e1;s2;e2;len;identity;ref_len;qry_len;...;edge_id;seed_id
			aln_parts = best['parts']  # 原始 MUMmer coords 输出的各字段
			aln_info = ';'.join(aln_parts)
			header = f">{self.base.name}_direct_overlap\tgap:{gap_length}\tlen:{len(final_seq)}\tAln:{aln_info}"

			with open(direct_connection_final, "w") as f:
				f.write(f"{header}\n{final_seq}\n")

			logfile.write(f"\n*** Found direct connection! ***\n")
			logfile.write(f"Connected edge: {edge_id}\n")
			logfile.write(f"Connected edge original length: {len(edge_seq)}bp\n")
			logfile.write(f"Seed original length: {len(seed_seq)}bp\n")
			logfile.write(f"Alignment region: {s1}-{e1} vs {s2}-{e2}\n")
			logfile.write(f"Alignment length: {length}bp, identity: {identity}%\n")
			logfile.write(f"GAP Length: {gap_length}\n")
			logfile.write(f"Direct connection sequence saved to: {direct_connection_final}\n")
			logfile.write("GAP can be closed!\n")
			logfile.write("Direct overlap\n")
			logfile.write("But will enter extension phase first, if extension phase fails or result gap length is negative, then use direct connection result\n")
			logfile.write("============================\n\n")

			self.has_direct_connection = True
			self.direct_connection_result = {
				"final_seq_file": direct_connection_final,
				"gap_length": gap_length,
				"overlap_length": length,
				"identity": identity,
				"connected_edge": edge_id
			}

			return True

		logfile.write("No valid direct connection found\n")
		logfile.write("============================\n\n")
		return False

