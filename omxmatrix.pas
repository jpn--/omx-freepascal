//  omxmatrix.pas
// 
//  OMX/HDF5 Matrix helper routines
// 
//  @author Jeff Newman, Cambridge Systematics
//  
//  Based on the c++ version, by
//  @author Billy Charlton, PSRC
//  @author Ben Stabler, RSG
// 

unit omxmatrix;

interface

{$DEFINE  MODE_READWRITE:= 0 }
{$DEFINE  MODE_CREATE   := 1 }
{$DEFINE  MAX_TABLES  := 500 }

uses
	fgl, hdf5dll;

type

PtrDouble = ^double;
TMapStringInt = specialize TFPGMap<String,Integer>;
TMapStringHID = specialize TFPGMap<String,hid_t>;

function isOMX(filename:string):Boolean;


TOMXMatrix = class(TObject)

public
    constructor Create();
    destructor Destroy(); override;

    procedure openFile(fileName:string);
    procedure closeFile();

    //Read/Open operations
    function  getRows(): Integer;
    function  getCols(): Integer;
    function  getTables(): Integer;
    procedure getRow(table:string, row:Integer, rowptr:Pointer);  // throws InvalidOperationException, MatrixReadException
    procedure getCol(table:string, col:Integer, colptr:Pointer);  // throws InvalidOperationException, MatrixReadException
    function  getTableName(table:Integer): String;

    //Write/Create operations
    procedure createFile(tables:Integer,  rows:Integer, cols:Integer, matNames:array of string, fileName:string);
    procedure writeRow(table:string,  row:Integer, rowptr:PtrDouble);

    //Nested exception classes
    class    FileOpenException { };
    class    MatrixReadException { };
    class    InvalidOperationException { };
    class    OutOfMemoryException {};
    class    NoSuchTableException {};

//--------------------------------------------------------------------
    //Data

    _h5file:hid_t;
    _nRows:Integer;
    _nCols:Integer;
    _nTables:Integer;
    _mode:Integer;
    _fileOpen:Boolean;

    _tableName:array[MAX_TABLES+1] of string;
    
    _tableLookup:TMapStringInt;
    _dataset:TMapStringHID;
    _dataspace:TMapStringHID;

private

	_memspace:hid_t;

    //Methods
    procedure readTableNames();
    procedure printErrorCode(error:Integer);
    procedure init_tables (tableNames:array of string);
    function  openDataset(table:string):hid_t;  // throws InvalidOperationException

end;




implementation
{ the implementation is the code to execute the interface commands above }


constructor TOMXMatrix.Create() 
begin
    _fileOpen := false;
    _nTables := 0;
    _nRows := 0;
    _nCols := 0;
    _memspace := -1;
end;

destructor TOMXMatrix.Destroy()
begin
    if (_memspace > -1 ) then begin
        H5Sclose(_memspace);
        _memspace = -1;
    end

    // Close H5 file handles
    if (_fileOpen==true) then begin
        H5Fclose(_h5file);
    end;

    _fileOpen = false;
end;

//Write/Create operations ---------------------------------------------------

procedure TOMXMatrix.createFile( tables:Integer,  rows:Integer,  cols:Integer, tableNames:array of string,  fileName:String) 
var
	shape:array[0..1] of Integer;
	plist:hid_t;
begin
    _fileOpen := true;
    _mode := MODE_CREATE;

    _nRows := rows;
    _nCols := cols;
    _nTables := tables;

    // Create the physical file - H5F_ACC_TRUNC = overwrite an existing file
    _h5file = H5Fcreate(fileName.c_str(), H5F_ACC_TRUNC, H5P_DEFAULT, H5P_DEFAULT);
    if (0 > _h5file) {
        fprintf(stderr, "ERROR: Could not create file %s.\n", fileName.c_str());
    }

    // Build SHAPE attribute
    shape[0] := rows;
    shape[1] := cols;

    // Write file attributes
    H5LTset_attribute_string(_h5file, "/", "OMX_VERSION", "0.2");
    H5LTset_attribute_int(_h5file, "/", "SHAPE", &shape[0], 2);
   
    // save the order that matrices are written
    plist := H5Pcreate (H5P_GROUP_CREATE);
    H5Pset_link_creation_order(plist, H5P_CRT_ORDER_TRACKED);
   
    // Create folder structure
    H5Gcreate(_h5file, "/data", NULL, plist, NULL);
    H5Gcreate(_h5file, "/lookup", NULL, plist, NULL);
    
    H5Pclose(plist);
    
    // Create the datasets
    init_tables(tableNames);
end;

procedure TOMXMatrix.writeRow( table:String,  row:Integer, double *rowdata) 
begin

	// First see if we've opened this table already
	if (_dataset.count(table) == 0) then begin
		// Does this table exist?
		if (_tableLookup.count(table) == 0) then begin
			throw NoSuchTableException();
		end;
		_dataset[table] = openDataset(table);
	end;

    hsize_t count[2], offset[2];

    count[0] = 1;
    count[1] = _nCols;

    offset[0] = row-1;
    offset[1] = 0;

    if (_memspace <0 ) then begin
    	_memspace = H5Screate_simple(2,count,NULL);
    end;

    if (_dataspace.count(table)==0) then begin
        _dataspace[table] = H5Dget_space(_dataset[table]);
    end;

    H5Sselect_hyperslab (_dataspace[table], H5S_SELECT_SET, offset, NULL, count, NULL);

    if (0 > H5Dwrite(_dataset[table], H5T_NATIVE_DOUBLE, _memspace, _dataspace[table], H5P_DEFAULT, rowdata)) then begin
        fprintf(stderr, "ERROR: writing table %s, row %d\n", table.c_str(), row);
        exit(2);
    end;
end;

//Read/Open operations ------------------------------------------------------

void OMXMatrix::openFile(string filename) 
var
	shape:array[0..1] of Integer;
	status:herr_t;
begin
    // Try to open the existing file
	_h5file = H5Fopen(filename.c_str(), H5F_ACC_RDWR, H5P_DEFAULT);
    if (_h5file < 0) then begin
        fprintf(stderr, "ERROR: Can't find or open file %s",filename.c_str());
        exit(2);
    end;

    // OK, it's open and it's HDF5;
    // Now query some things about the file.
    _fileOpen := true;
	_mode := MODE_READWRITE;

    status := 0;
    status += H5LTget_attribute_int(_h5file, "/", "SHAPE", &shape[0]);
    if (status < 0) then begin
        fprintf(stderr, "ERROR: %s doesn't have SHAPE attribute\n", filename.c_str());
        exit(2);
    end;
    _nRows := shape[0];
    _nCols := shape[1];

    readTableNames();
end

function TOMXMatrix.OMXMatrix::getRows():Integer 
begin
    return _nRows;
end;

function TOMXMatrix.OMXMatrix::getCols() :Integer
begin
    return _nCols;
end;

function TOMXMatrix.OMXMatrix::getTables() :Integer
begin
    return _nTables;
end;

function TOMXMatrix.getTableName( table:Integer):String 
begin
    return _tableName[table];
end;

void OMXMatrix::getRow ( table:String,  row:Integer, rowptr:Pointer) 
var
	data_count:array[0..1] of hsize_t;
	data_offset:array[0..1] of hsize_t;
begin

    // First see if we've opened this table already
    if (_dataset.count(table)==0) then begin
        // Does this table exist?
        if (_tableLookup.count(table)==0) then begin
            throw MatrixReadException() ;
        end;
        _dataset[table] = openDataset(table);
    end;

    data_count[0] := 1;
    data_count[1] := _nCols;
    data_offset[0] := row-1;
    data_offset[1] := 0;

    // Create dataspace if necessary.  Don't do every time or we'll run OOM.
    if (_dataspace.count(table)==0) then begin
        _dataspace[table] = H5Dget_space(_dataset[table]);
    end;

    // Define MEMORY slab (using data_count since we don't want to read zones+1 values!)
    if (_memspace < 0) then begin
        _memspace := H5Screate_simple(2, data_count, NULL);
    end;

    // Define DATA slab
    if (0 > H5Sselect_hyperslab (_dataspace[table], H5S_SELECT_SET, data_offset, NULL, data_count, NULL)) then begin
        fprintf(stderr, "ERROR: Couldn't select DATA subregion for table %s, subrow %d.\n",
                table.c_str(),row);
        exit(2);
    end;

    // Read the data!
    if (0 > H5Dread(_dataset[table], H5T_NATIVE_DOUBLE, _memspace, _dataspace[table],
            H5P_DEFAULT, rowptr)) then begin
        fprintf(stderr, "ERROR: Couldn't read table %s, subrow %d.\n",table.c_str(),row);
        exit(2);
    end;
end;

procedure OMXMatrix.getCol( table:String,  col:Integer, colptr:Pointer) 
var
	data_count:array[0..1] of hsize_t;
	data_offset:array[0..1] of hsize_t;
begin

	// First see if we've opened this table already
	if (_dataset.count(table) == 0) then begin
		// Does this table exist?
		if (_tableLookup.count(table) == 0) then begin
			throw MatrixReadException();
		end;
		_dataset[table] = openDataset(table);
	end

	data_count[0] := _nRows;
	data_count[1] := 1;
	data_offset[0] := 0;
	data_offset[1] := col - 1;

	// Create dataspace if necessary.  Don't do every time or we'll run OOM.
	if (_dataspace.count(table) == 0) then begin
		_dataspace[table] = H5Dget_space(_dataset[table]);
	end;

	// Define MEMORY slab (using data_count since we don't want to read zones+1 values!)
	if (_memspace < 0) then begin
		_memspace = H5Screate_simple(2, data_count, NULL);
	end;

	// Define DATA slab
	if (0 > H5Sselect_hyperslab(_dataspace[table], H5S_SELECT_SET, data_offset, NULL, data_count, NULL)) then begin
		fprintf(stderr, "ERROR: Couldn't select DATA subregion for table %s, subcol %d.\n",
			table.c_str(), col);
		exit(2);
	end;

	// Read the data!
	if (0 > H5Dread(_dataset[table], H5T_NATIVE_DOUBLE, _memspace, _dataspace[table],
		H5P_DEFAULT, colptr)) then begin
		fprintf(stderr, "ERROR: Couldn't read table %s, subcol %d.\n", table.c_str(), col);
		exit(2);
	end;
end;

procedure TOMXMatrix.closeFile() 
begin
    for(map<string,hid_t>::iterator iterator = _dataset.begin(); iterator != _dataset.end(); iterator++) then begin
        H5Dclose(iterator->second);
    end;

    for(map<string,hid_t>::iterator iterator = _dataspace.begin(); iterator != _dataspace.end(); iterator++) then begin
        H5Sclose(iterator->second);
    end;

    if (_memspace > -1 ) then begin
        H5Sclose(_memspace);
        _memspace = -1;
    end;

    if (_fileOpen==true) then begin
        H5Fclose(_h5file);
    end;
    _fileOpen = false;
end;

// ---- Private functions ---------------------------------------------------

hid_t OMXMatrix::openDataset(string table) 
begin

    string tname = "/data/" + table;
    
    hid_t dataset = H5Dopen(_h5file, tname.c_str(), H5P_DEFAULT);
    if (dataset < 0) {
        throw InvalidOperationException();
    }

    return dataset;
end;

//
// Group traversal function. Build list of tablenames from this.
// 
herr_t _leaf_info(hid_t loc_id, const char *name, const H5L_info_t *info, void *opdata)
begin
    OMXMatrix *m = (OMXMatrix *) opdata;

    m->_nTables++;
    m->_tableName[m->_nTables] = name;
    m->_tableLookup[name] = m->_nTables;
    return 0;
end;

// Read table names.  Sets number of tables in file, too. 
procedure TOMXMatrix.readTableNames() 
var
	datagroup:hid_t;
	info:hid_t;
begin

    _nTables := 0;
    _tableLookup.clear();
    _dataset.clear();
    _dataspace.clear();
    unsigned flags = 0;

    datagroup := H5Gopen(_h5file, "/data", H5P_DEFAULT);

    // if group has creation-order index, use it
    info := H5Gget_create_plist(datagroup);
    H5Pget_link_creation_order(info, &flags);
    H5Pclose(info);

    if (flags & H5P_CRT_ORDER_TRACKED) then begin
    	// Call _leaf_info() for every child in /data:
        H5Literate(datagroup, H5_INDEX_CRT_ORDER, H5_ITER_INC, NULL, _leaf_info, this);
    end else begin
    	// otherwise just use name order
    	H5Literate(datagroup, H5_INDEX_NAME, H5_ITER_INC, NULL, _leaf_info, this);
    end;

    H5Gclose(datagroup);
end;



void OMXMatrix::init_tables (tableNames:array of string) 
begin

    hsize_t     dims[2]={_nRows,_nCols};
    hid_t       plist;
    herr_t      rtn;
    hsize_t     chunksize[2];
    double      fillvalue[1];

    fillvalue[0] = 0.0;
    chunksize[0] = 1;
    chunksize[1] = _nCols;

    hid_t   dataspace = H5Screate_simple(2,dims, NULL);

    // Use a row-chunked, zip-compressed data format:
    plist = H5Pcreate(H5P_DATASET_CREATE);
    rtn = H5Pset_chunk(plist, 2, chunksize);
    rtn = H5Pset_deflate(plist, 7);
    rtn = H5Pset_fill_value(plist, H5T_NATIVE_DOUBLE, &fillvalue);

    // Loop on all tables
    for (unsigned int t=0; t<tableNames.size(); t++) then begin
        string tpath = "/data/" + tableNames[t];
        string tname(tableNames[t]);
        
        // Create a dataset for each table
        _dataset[tname] = H5Dcreate2(_h5file, tpath.c_str(), H5T_NATIVE_DOUBLE,
                                 dataspace, H5P_DEFAULT, plist, H5P_DEFAULT);
        if (_dataset[tname]<0) then begin
            fprintf(stderr, "Error creating dataset %s",tpath.c_str());
            exit(2);
        end;
        
        // Save the something somewhere
        _tableLookup[tname] = t+1;
    end;

    rtn = H5Pclose(plist);
    rtn = H5Sclose(dataspace);
end;

function isOMX(filename:string):Boolean
var
	answer:htri_t;
	f:hid_t;
	exists:herr_t;
begin
	answer = H5Fis_hdf5(filename);
	if (answer <= 0) then return false;

	// It's HDF5; is it OMX?
	f := H5Fopen(filename, H5F_ACC_RDONLY, H5P_DEFAULT);
	exists := H5LTfind_attribute(f, "OMX_VERSION");

	//don't actually care what OMX version it is, yet...
	//char version[255];
	//int status = H5LTget_attribute_string(f,"/","OMX_VERSION", version);
	H5Fclose(f);

	if (exists == 0)  then begin
		fprintf(stderr, "\n** %s is HDF5, but is not a valid OMX file.\n", filename);
		exit(2);
	end;

	return true;
end;
