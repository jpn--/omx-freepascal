program OMX_Example;

uses omxmatrix;

{$MACRO ON}
{$DEFINE MAXZONES:= 8000}

type
  POMXMatrix = ^TOMXMatrix;

var
  omxMfsFileName:String;
  omxMfs:TOMXMatrix;
  omxDataBuffer:array[0..MAXZONES+1] of Double;    //OMX is doubles
  i,zones:Integer;
  tableNames:array[1..3] of string;

begin
  writeln('Running OMX_Example.');


  omxMfsFileName := 'C:\tmp\omx-test\examp.omx';

  tableNames[1] := 'First';
  tableNames[2] := 'Second';
  tableNames[3] := 'Third';









  //* open omx file as read/write */
  writeln('Creating file ',omxMfsFileName);
  omxMfs := TOMXMatrix.Create();
  omxMfs.createFile(3, 7000, 7000, tableNames, omxMfsFileName);

 // writeln(omxMfsFileName, ' as OMX file: ', isOMX(omxMfsFileName));

  //if (isOMX(omxMfsFileName)) then begin
  //  omxMfs.openFile(omxMfsFileName);
  //end else begin
  //  writeln('error: cannot open OMX mfs file.\n');
  //end;

  //* initialize omx data buffer */
  writeln('initialize omx data buffer ',MAXZONES);
  for i := 0 to MAXZONES + 1 do begin
    omxDataBuffer[i] := 0.0;
  end;

  //* get number of zones */
  zones := omxMfs.getRows();
  writeln('get number of zones = ',zones);

  //* read and write row 2 */
  omxMfs.getRow('First', 2, @(omxDataBuffer[0]));
  //



  for i := 0 to 16 do begin
    omxDataBuffer[i] := i*101.0;
    writeln(i,' is ',omxDataBuffer[i]);
  end;

  omxMfs.writeRow('First', 11, omxDataBuffer);

  omxMfs.closeFile();

  writeln('Finished OMX_Example.');
end.

