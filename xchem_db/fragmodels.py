#! /dls/science/users/tyt15771/miniconda3/envs/xcdb/bin/python

# 8-Apr-20
# Anna Carbery


import os
#import django
#os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
#os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
#django.setup()
#from xchem_db.models import *
#from __future__ import unicode_literals

from django.db import models
from django.contrib.postgres.fields import ArrayField


class Target(models.Model):
	target_name = models.CharField(max_length=255, unique=True, db_index=True) # must be unique!!
	aa_sequence = models.CharField(max_length=10000, unique=True, db_index=True) # how to set max length? 
	reference_pdbs = [] # may be more than one - how to handle?
	hits = [] # link to compounds
	misses = [] # link to compounds
	bound_pdbs = [] # pdb files of hits in bound state


class Compound(models.Model):
	smiles = models.CharField(max_length=255, unique=True, db_index=True) # canonicalised!! must be unique!!
	inchi = None # how do I store this information ?? 
	DSiP = models.BooleanField(default=False)
	DSPL = models.BooleanField(default=False)


class Crystal(models.Model):
	# do I need a crystal name?
	target = models.ForeignKey(Target, on_delete=models.CASCADE)
	compound = models.ForeignKey(Compound, on_delete=models.CASCADE)
	fragdir = models.CharField(max_length=255, unique=True, db_index=True) # directory created when there is a hit
	reference = models.ForeignKey(PDB, on_delete=models.CASCADE)
	outcome = models.ForeignKey(Outcome, on_delete=models.CASCADE) # is this necessary? maybe the best we can do at the moment
	visit = models.ForeignKey(Visit, on_delete=models.CASCADE)


class Visit(models.Model):
	visit_name = models.CharField(max_length=255, unique=True, db_index=True)


class Outcome(models.Model):
	OUTCOME_CHOICES = [
		('0', 'No result'),
		('1', 'analysis pending'),
		('2', 'pandda model'),
		('3', 'in refinement'),
		('4', 'comp chem ready'),
		('5', 'ready for deposition'),
		('6', 'deposited')
		]
	outcome = models.Charfield(max_length=1, choices=OUTCOME_CHOICES, default='0')	
	hit = models.BooleanField(default=False)




