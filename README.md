
The Free Pascal API does more than the simple example below, although not a lot more.  
Refer to the source code for more information.

```
program OMX_Example;

uses omxmatrix;

{$MACRO ON}
{$DEFINE MAXZONES:= 1000}

var
  omxMfsFileName:String;
  omxMfs:TOMXMatrix;
  omxDataBuffer:array[0..MAXZONES+1] of Double;    //OMX is doubles
  i,zones:Integer;
  tableNames:array[1..3] of string;

begin

  omxMfsFileName := 'C:\tmp\omx-test\examp.omx';

  tableNames[1] := 'First';
  tableNames[2] := 'Second';
  tableNames[3] := 'Third';

  //* open omx file as read/write */
  writeln('Creating file ',omxMfsFileName);
  omxMfs := TOMXMatrix.Create();
  omxMfs.createFile(3, 700, 700, tableNames, omxMfsFileName);

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

  //* write some junk data in the buffer */
  for i := 0 to 16 do begin
    omxDataBuffer[i] := i*101.0;
    writeln(i,' is ',omxDataBuffer[i]);
  end;

  omxMfs.writeRow('First', 2, omxDataBuffer);

  omxMfs.closeFile();

  writeln('Finished OMX_Example.');
end.
```
