# inner-circle-db-backupper
A repository with functionality for periodically creating backups of PostgreSQL databases.

More information about the project and related repositories can be found here:
[inner-circle-documentation](https://github.com/TourmalineCore/inner-circle-documentation/)

## Helm Template Debug

### To render the chart
```bash
helm template ./ci --debug
```

### To build the chart into a package
```bash
helm package ./ci
```

## Additional information

### Backups naming convention

We used two different naming conventions.

In the first convention, the backup creation date and time were used as a prefix in the SQL dump filenames. Since dumps from all services are stored in a single archive, this makes it easier to sort and identify files by service name within the archive, as all backups were created around the same time.

In the second convention, the archive creation date and time were used as a prefix in the archive filename. Since the directory contains only archives belonging to the same project, this makes it easier to find a specific archive based on its creation time.