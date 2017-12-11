import luigi
import psycopg2
import sqlite3
import subprocess
import sys
import os
import datetime
import pandas
from sqlalchemy import create_engine
import logging


class FindSoakDBFiles(luigi.Task):
    # date parameter - needs to be changed
    date = luigi.DateParameter(default=datetime.date.today())

    # filepath parameter can be changed elsewhere
    filepath = luigi.Parameter(default="/dls/labxchem/data/*/lb*/*")

    def output(self):
        return luigi.LocalTarget(self.date.strftime('soakDBfiles/soakDB_%Y%m%d.txt'))

    def run(self):
        # maybe change to *.sqlite to find renamed files? - this will probably pick up a tonne of backups
        process = subprocess.Popen(str('''find ''' + self.filepath +  ''' -maxdepth 5 -path "*/lab36/*" -prune -o -path "*/initial_model/*" -prune -o -path "*/beamline/*" -prune -o -path "*/analysis/*" -prune -o -path "*ackup*" -prune -o -path "*old*" -prune -o -path "*TeXRank*" -prune -o -name "soakDBDataFile.sqlite" -print'''),
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)

        # run process to find sqlite files
        out, err = process.communicate()

        # print output and error for debugging
        #print out
        #print err

        # write filepaths to file as output
        with self.output().open('w') as f:
            f.write(out)
        #f.close()


class TransferFedIDs(luigi.Task):
    # date parameter for daily run - needs to be changed
    date = luigi.DateParameter(default=datetime.date.today())

    # needs a list of soakDB files from the same day
    def requires(self):
        return FindSoakDBFiles()

    # output is just a log file
    def output(self):
        return luigi.LocalTarget(self.date.strftime('transfer_logs/fedids_%Y%m%d.txt'))

    # transfers data to a central postgres db
    def run(self):
        # connect to central postgres db
        conn = psycopg2.connect('dbname=xchem user=uzw12877 host=localhost')
        c = conn.cursor()
        # create a table to hold info on sqlite files
        c.execute('''CREATE TABLE IF NOT EXISTS soakdb_files (filename TEXT, modification_date BIGINT, proposal TEXT)'''
                  )
        conn.commit()

        # set up logging
        logfile = self.date.strftime('transfer_logs/fedids_%Y%m%d.txt')
        logging.basicConfig(filename=logfile, level=logging.DEBUG, format='%(asctime)s %(message)s',
                            datefrmt='%m/%d/%y %H:%M:%S')

        # use list from previous step as input to write to postgres
        with self.input().open('r') as database_list:
            for database_file in database_list.readlines():
                database_file = database_file.replace('\n', '')

                # take proposal number from filepath (for whitelist)
                proposal = database_file.split('/')[5].split('-')[0]
                proc = subprocess.Popen(str('getent group ' + str(proposal)), stdout=subprocess.PIPE, shell=True)
                out, err = proc.communicate()

                # need to put modification date to use in the proasis upload scripts
                modification_date = datetime.datetime.fromtimestamp(os.path.getmtime(database_file)).strftime(
                    "%Y-%m-%d %H:%M:%S")
                modification_date = modification_date.replace('-', '')
                modification_date = modification_date.replace(':', '')
                modification_date = modification_date.replace(' ', '')
                c.execute('''INSERT INTO soakdb_files (filename, modification_date, proposal) SELECT %s,%s,%s WHERE NOT EXISTS (SELECT filename, modification_date FROM soakdb_files WHERE filename = %s AND modification_date = %s)''', (database_file, int(modification_date), proposal, database_file, int(modification_date)))
                conn.commit()

                logging.info(str('FedIDs written for ' + proposal))

        c.execute('CREATE TABLE IF NOT EXISTS proposals (proposal TEXT, fedids TEXT)')

        proposal_list = []
        c.execute('SELECT proposal FROM soakdb_files')
        rows = c.fetchall()
        for row in rows:
            proposal_list.append(str(row[0]))

        for proposal_number in set(proposal_list):
            proc = subprocess.Popen(str('getent group ' + str(proposal_number)), stdout=subprocess.PIPE, shell=True)
            out, err = proc.communicate()
            append_list = out.split(':')[3].replace('\n', '')

            c.execute(str('''INSERT INTO proposals (proposal, fedids) SELECT %s, %s WHERE NOT EXISTS (SELECT proposal, fedids FROM proposals WHERE proposal = %s AND fedids = %s);'''), (proposal_number, append_list, proposal_number, append_list))
            conn.commit()

        c.close()

        with self.output().open('w') as f:
            f.write('TransferFeDIDs DONE')


class TransferExperiment(luigi.Task):
    # date parameter - needs to be changed
    date = luigi.DateParameter(default=datetime.date.today())

    # needs soakDB list, but not fedIDs - this task needs to be spawned by soakDB class
    def requires(self):
        return FindSoakDBFiles()

    def output(self):
        return luigi.LocalTarget(self.date.strftime('transfer_logs/transfer_experiment_%Y%m%d.txt'))

    def run(self):
        # set up logging
        logfile = self.date.strftime('transfer_logs/transfer_experiment_%Y%m%d.txt')
        logging.basicConfig(filename=logfile, level=logging.DEBUG, format='%(asctime)s %(message)s', datefrmt='%m/%d/%y %H:%M:%S')

        def create_list_from_ind(row, array, numbers_list, crystal_id):
            for ind in numbers_list:
                array.append(row[ind])
            array.append(crystal_id)

        def pop_dict(array, dictionary, dictionary_keys):
            for i in range(0, len(dictionary_keys)):
                dictionary[dictionary_keys[i]].append(array[i])
            return dictionary

        def add_keys(dictionary, keys):
            for key in keys:
                dictionary[key] = []

        lab_dict = {}
        crystal_dict = {}
        data_collection_dict = {}
        data_processing_dict = {}
        dimple_dict = {}
        refinement_dict = {}

        # define keys for xchem postgres DB
        lab_dictionary_keys = ['visit', 'library_plate', 'library_name', 'smiles', 'compound_code', 'protein',
                               'stock_conc', 'expr_conc',
                               'solv_frac', 'soak_vol', 'soak_status', 'cryo_Stock_frac', 'cryo_frac',
                               'cryo_transfer_vol', 'cryo_status',
                               'soak_time', 'harvest_status', 'crystal_name', 'mounting_result', 'mounting_time',
                               'data_collection_visit', 'crystal_id']

        crystal_dictionary_keys = ['tag', 'name', 'spacegroup', 'point_group', 'a', 'b', 'c', 'alpha',
                                   'beta', 'gamma', 'volume', 'crystal_name', 'crystal_id']

        data_collection_dictionary_keys = ['date', 'outcome', 'wavelength', 'crystal_name', 'crystal_id']

        data_processing_dictionary_keys = ['image_path', 'program', 'spacegroup', 'unit_cell', 'auto_assigned',
                                           'res_overall',
                                           'res_low', 'res_low_inner_shell', 'res_high', 'res_high_15_sigma',
                                           'res_high_outer_shell',
                                           'r_merge_overall', 'r_merge_low', 'r_merge_high', 'isig_overall', 'isig_low',
                                           'isig_high', 'completeness_overall', 'completeness_low', 'completeness_high',
                                           'multiplicity_overall', 'multiplicity_low', 'multiplicity_high',
                                           'cchalf_overall',
                                           'cchalf_low', 'cchalf_high', 'logfile_path', 'mtz_path', 'log_name',
                                           'mtz_name',
                                           'original_directory', 'unique_ref_overall', 'lattice', 'point_group',
                                           'unit_cell_vol',
                                           'alert', 'score', 'status', 'r_cryst', 'r_free', 'dimple_pdb_path',
                                           'dimple_mtz_path',
                                           'dimple_status', 'crystal_name', 'crystal_id']

        dimple_dictionary_keys = ['res_high', 'r_free', 'pdb_path', 'mtz_path', 'reference_pdb', 'status', 'pandda_run',
                                  'pandda_hit',
                                  'pandda_reject', 'pandda_path', 'crystal_name', 'crystal_id']

        refinement_dictionary_keys = ['res', 'res_TL', 'rcryst', 'rcryst_TL', 'r_free', 'rfree_TL', 'spacegroup',
                                      'lig_cc', 'rmsd_bonds',
                                      'rmsd_bonds_TL', 'rmsd_angles', 'rmsd_angles_TL', 'outcome', 'mtz_free', 'cif',
                                      'cif_status', 'cif_prog',
                                      'pdb_latest', 'mtz_latest', 'matrix_weight', 'refinement_path', 'lig_confidence',
                                      'lig_bound_conf', 'bound_conf', 'molprobity_score', 'molprobity_score_TL',
                                      'ramachandran_outliers', 'ramachandran_outliers_TL', 'ramachandran_favoured',
                                      'ramachandran_favoured_TL', 'status', 'crystal_name', 'crystal_id']


        dictionaries = [[lab_dict, lab_dictionary_keys], [crystal_dict, crystal_dictionary_keys],
                        [data_collection_dict, data_collection_dictionary_keys],
                        [data_processing_dict, data_processing_dictionary_keys],
                        [dimple_dict, dimple_dictionary_keys], [refinement_dict, refinement_dictionary_keys]]

        # add keys to dictionaries
        for dictionary in dictionaries:
            add_keys(dictionary[0], dictionary[1])

        # some filters to get rid of junk
        soakstatus = 'done'
        cryostatus = 'pending'
        mountstatus = '%Mounted%'
        collectionstatus = '%success%'
        compsmiles = '%None%'

        # numbers relating to where selected in query
        # 17 = number for crystal_name
        lab_table_numbers = range(0, 21)

        crystal_table_numbers = range(22, 33)
        crystal_table_numbers.insert(len(crystal_table_numbers), 17)

        data_collection_table_numbers = range(33, 36)
        data_collection_table_numbers.insert(len(data_collection_table_numbers), 17)

        data_processing_table_numbers = range(36, 79)
        data_processing_table_numbers.insert(len(data_processing_table_numbers), 17)

        dimple_table_numbers = range(79, 89)
        dimple_table_numbers.insert(len(dimple_table_numbers), 17)

        refinement_table_numbers = range(91, 122)
        refinement_table_numbers.insert(len(refinement_table_numbers), 17)

        # connect to master postgres db
        conn = psycopg2.connect('dbname=xchem user=uzw12877 host=localhost')
        c = conn.cursor()

        # get all soakDB file names and close postgres connection
        c.execute('select filename from soakdb_files')
        rows = c.fetchall()
        c.close()

        crystal_list = []

        # set database filename from postgres query
        for row in rows:
            database_file = str(row[0])

            # connect to soakDB
            conn2 = sqlite3.connect(str(database_file))
            c2 = conn2.cursor()

            try:
                # columns with issues: ProjectDirectory, DatePANDDAModelCreated

                for row in c2.execute('''select LabVisit, LibraryPlate, LibraryName, CompoundSMILES, CompoundCode,
                                        ProteinName, CompoundStockConcentration, CompoundConcentration, SolventFraction, 
                                        SoakTransferVol, SoakStatus, CryoStockFraction, CryoFraction, CryoTransferVolume, 
                                        CryoStatus, SoakingTime, HarvestStatus, CrystalName, MountingResult, MountingTime, 
                                        DataCollectionVisit, 

                                        ProjectDirectory, 

                                        CrystalTag, CrystalFormName, CrystalFormSpaceGroup,
                                        CrystalFormPointGroup, CrystalFormA, CrystalFormB, CrystalFormC,CrystalFormAlpha, 
                                        CrystalFormBeta, CrystalFormGamma, CrystalFormVolume, 

                                        DataCollectionDate, 
                                        DataCollectionOutcome, DataCollectionWavelength, 

                                        DataProcessingPathToImageFiles,
                                        DataProcessingProgram, DataProcessingSpaceGroup, DataProcessingUnitCell,
                                        DataProcessingAutoAssigned, DataProcessingResolutionOverall, DataProcessingResolutionLow,
                                        DataProcessingResolutionLowInnerShell, DataProcessingResolutionHigh, 
                                        DataProcessingResolutionHigh15Sigma, DataProcessingResolutionHighOuterShell, 
                                        DataProcessingRMergeOverall, DataProcessingRMergeLow, DataProcessingRMergeHigh, 
                                        DataProcessingIsigOverall, DataProcessingIsigLow, DataProcessingIsigHigh, 
                                        DataProcessingCompletenessOverall, DataProcessingCompletenessLow,
                                        DataProcessingCompletenessHigh, DataProcessingMultiplicityOverall, 
                                        DataProcessingMultiplicityLow, DataProcessingMultiplicityHigh, 
                                        DataProcessingCChalfOverall, DataProcessingCChalfLow, DataProcessingCChalfHigh, 
                                        DataProcessingPathToLogFile, DataProcessingPathToMTZfile, DataProcessingLOGfileName, 
                                        DataProcessingMTZfileName, DataProcessingDirectoryOriginal,
                                        DataProcessingUniqueReflectionsOverall, DataProcessingLattice, DataProcessingPointGroup,
                                        DataProcessingUnitCellVolume, DataProcessingAlert, DataProcessingScore,
                                        DataProcessingStatus, DataProcessingRcryst, DataProcessingRfree, 
                                        DataProcessingPathToDimplePDBfile, DataProcessingPathToDimpleMTZfile,
                                        DataProcessingDimpleSuccessful, 

                                        DimpleResolutionHigh, DimpleRfree, DimplePathToPDB,
                                        DimplePathToMTZ, DimpleReferencePDB, DimpleStatus, DimplePANDDAwasRun, 
                                        DimplePANDDAhit, DimplePANDDAreject, DimplePANDDApath, 

                                        PANDDAStatus, DatePANDDAModelCreated, 

                                        RefinementResolution, RefinementResolutionTL, 
                                        RefinementRcryst, RefinementRcrystTraficLight, RefinementRfree, 
                                        RefinementRfreeTraficLight, RefinementSpaceGroup, RefinementLigandCC, 
                                        RefinementRmsdBonds, RefinementRmsdBondsTL, RefinementRmsdAngles, RefinementRmsdAnglesTL,
                                        RefinementOutcome, RefinementMTZfree, RefinementCIF, RefinementCIFStatus, 
                                        RefinementCIFprogram, RefinementPDB_latest, RefinementMTZ_latest, RefinementMatrixWeight, 
                                        RefinementPathToRefinementFolder, RefinementLigandConfidence, 
                                        RefinementLigandBoundConformation, RefinementBoundConformation, RefinementMolProbityScore,
                                        RefinementMolProbityScoreTL, RefinementRamachandranOutliers, 
                                        RefinementRamachandranOutliersTL, RefinementRamachandranFavored, 
                                        RefinementRamachandranFavoredTL, RefinementStatus

                                        from mainTable 
                                        '''):

                    try:
                        if str(row[17]) in crystal_list:
                            crystal_name = row[17].replace(str(row[17]), str(str(row[17]) + 'I'))
                        if str(row[17].replace(str(row[17]), str(str(row[17]) + 'I'))) in crystal_list:
                            crystal_name = row[17].replace(str(row[17]), str(str(row[17]) + 'II'))
                            print 'double whammy'
                        else:
                            crystal_name = row[17]

                        crystal_list.append(row[17])
                        crystal_list = list(set(crystal_list))
                    except:
                        print sys.exc_info()


                    lab_table_list = []
                    crystal_table_list = []
                    data_collection_table_list = []
                    data_processing_table_list = []
                    dimple_table_list = []
                    refinement_table_list = []

                    lists = [lab_table_list, crystal_table_list, data_collection_table_list, data_processing_table_list,
                             dimple_table_list, refinement_table_list]

                    numbers = [lab_table_numbers, crystal_table_numbers, data_collection_table_numbers,
                               data_processing_table_numbers, dimple_table_numbers, refinement_table_numbers]
                    listref = 0

                    for listname in lists:
                        create_list_from_ind(row, listname, numbers[listref], crystal_name)
                        listref += 1

                    # populate query return into dictionary, so that it can be turned into a df and transfered to DB
                    pop_dict(lab_table_list, lab_dict, lab_dictionary_keys)
                    pop_dict(crystal_table_list, crystal_dict, crystal_dictionary_keys)
                    pop_dict(refinement_table_list, refinement_dict, refinement_dictionary_keys)
                    pop_dict(dimple_table_list, dimple_dict, dimple_dictionary_keys)
                    pop_dict(data_collection_table_list, data_collection_dict,
                             data_collection_dictionary_keys)
                    pop_dict(data_processing_table_list, data_processing_dict,
                             data_processing_dictionary_keys)


            except:
                logging.warning(str('Database file: ' + database_file + ' WARNING: ' + str(sys.exc_info()[1])))
                c2.close()

        # turn dictionaries into dataframes
        labdf = pandas.DataFrame.from_dict(lab_dict)
        # crystaldf = pandas.DataFrame.from_dict(crystal_dict)
        dataprocdf = pandas.DataFrame.from_dict(data_processing_dict)
        # datacoldf = pandas.DataFrame.from_dict(data_collection_dict)
        refdf = pandas.DataFrame.from_dict(refinement_dict)
        dimpledf = pandas.DataFrame.from_dict(dimple_dict)

        # create an engine to postgres database and populate tables - ids are straight from dataframe index,
        # but link all together
        # TODO:
        # find way to do update, rather than just create table each time
        engine = create_engine('postgresql://uzw12877@localhost:5432/xchem')
        labdf.to_sql('lab', engine, if_exists='replace')
        # crystaldf.to_sql('crystal', engine, if_exists='replace')
        dataprocdf.to_sql('data_processing', engine, if_exists='replace')
        # datacoldf.to_sql('data_collection', engine, if_exists='replace')
        refdf.to_sql('refinement', engine, if_exists='replace')
        dimpledf.to_sql('dimple', engine, if_exists='replace')

        # connect to master postgres db
        conn = psycopg2.connect('dbname=xchem user=uzw12877 host=localhost')
        c = conn.cursor()

        with self.output().open('w') as f:
            f.write('TransferExperiment DONE')
